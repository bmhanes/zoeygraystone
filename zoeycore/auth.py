import msal
import jwt
import os
import logging
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("zoey.auth")

# ── Config ─────────────────────────────────────────────────────────────────────
AZURE_CLIENT_ID     = os.environ.get("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")
AZURE_TENANT_ID     = os.environ.get("AZURE_TENANT_ID", "")
AZURE_REDIRECT_URI  = os.environ.get("AZURE_REDIRECT_URI", "http://localhost:8000/auth/callback")
ZOEY_AD_GROUP       = os.environ.get("ZOEY_AD_GROUP", "zoey_users")

AUTHORITY = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
SCOPES    = ["User.Read"]

JWT_SECRET    = os.environ.get("JWT_SECRET", "change_this_secret_in_env")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_H  = int(os.environ.get("JWT_EXPIRY_HOURS", "8"))

security = HTTPBearer()

# ── MSAL ───────────────────────────────────────────────────────────────────────
def _msal_app() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        AZURE_CLIENT_ID,
        authority=AUTHORITY,
        client_credential=AZURE_CLIENT_SECRET,
    )


def get_auth_url() -> str:
    """Return the Microsoft login URL to redirect the user to."""
    return _msal_app().get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri=AZURE_REDIRECT_URI,
    )


# ── Azure Authentication ───────────────────────────────────────────────────────
async def authenticate_azure(code: str) -> dict:
    """
    Exchange an Azure AD authorization code for tokens, fetch user profile
    and group membership from Microsoft Graph, enforce zoey_users membership,
    and return a user info dict on success.
    """
    result = _msal_app().acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=AZURE_REDIRECT_URI,
    )

    if "error" in result:
        logger.error(f"Azure token exchange failed: {result.get('error_description')}")
        raise HTTPException(status_code=401, detail="Azure authentication failed")

    access_token = result["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        me_resp = await client.get("https://graph.microsoft.com/v1.0/me", headers=headers)
        if me_resp.status_code != 200:
            logger.error(f"Graph /me error {me_resp.status_code}: {me_resp.text}")
            raise HTTPException(status_code=503, detail="Failed to retrieve user profile")
        me = me_resp.json()

        groups_resp = await client.get(
            "https://graph.microsoft.com/v1.0/me/memberOf?$select=displayName",
            headers=headers,
        )
        if groups_resp.status_code != 200:
            logger.error(f"Graph /memberOf error {groups_resp.status_code}: {groups_resp.text}")
            raise HTTPException(status_code=503, detail="Failed to retrieve group membership")
        group_names = [g.get("displayName", "") for g in groups_resp.json().get("value", [])]

    upn      = me.get("userPrincipalName", "")
    username = upn.split("@")[0].lower()

    if ZOEY_AD_GROUP not in group_names:
        logger.warning(f"Access denied for {upn} — not in '{ZOEY_AD_GROUP}'")
        raise HTTPException(
            status_code=403,
            detail="Access denied — your account is not authorized for Zoey",
        )

    user = {
        "username":     username,
        "upn":          upn,
        "display_name": me.get("displayName", ""),
        "email":        me.get("mail") or upn,
        "department":   me.get("department", ""),
        "title":        me.get("jobTitle", ""),
        "groups":       group_names,
    }

    logger.info(f"Access granted: {user['display_name']} ({upn})")
    return user


# ── JWT Token ──────────────────────────────────────────────────────────────────
def create_jwt(user: dict) -> str:
    """Issue a signed JWT for an authenticated user."""
    payload = {
        "sub":          user["username"],
        "upn":          user.get("upn", ""),
        "display_name": user["display_name"],
        "email":        user["email"],
        "department":   user["department"],
        "title":        user["title"],
        "iat":          datetime.now(timezone.utc),
        "exp":          datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_H),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    FastAPI dependency — validates Bearer token on protected routes.
    Returns decoded payload on success.
    """
    token = credentials.credentials
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired — please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
