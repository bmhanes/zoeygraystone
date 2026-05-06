import msal
import jwt
import os
import logging
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("zoey.auth")

# ── Entra ID Config ────────────────────────────────────────────────────────────
ENTRA_TENANT_ID     = os.environ.get("ENTRA_TENANT_ID",     "")
ENTRA_CLIENT_ID     = os.environ.get("ENTRA_CLIENT_ID",     "")
ENTRA_CLIENT_SECRET = os.environ.get("ENTRA_CLIENT_SECRET", "")
ENTRA_AUTHORITY     = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}"
ENTRA_REDIRECT_URI  = os.environ.get("ENTRA_REDIRECT_URI",  "http://localhost:8000/auth/callback")
ENTRA_SCOPES        = [
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/GroupMember.Read.All"
]
ZOEY_AD_GROUP       = os.environ.get("ZOEY_AD_GROUP", "zoey_users")

# ── JWT Config ─────────────────────────────────────────────────────────────────
JWT_SECRET    = os.environ.get("JWT_SECRET",      "change_this_secret_in_env")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_H  = int(os.environ.get("JWT_EXPIRY_HOURS", "8"))

security = HTTPBearer()

# ── MSAL Confidential Client ───────────────────────────────────────────────────
def get_msal_app() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        client_id=ENTRA_CLIENT_ID,
        client_credential=ENTRA_CLIENT_SECRET,
        authority=ENTRA_AUTHORITY
    )

# ── Step 1: Generate Microsoft login URL ──────────────────────────────────────
def get_auth_url(state: str = "") -> str:
    """
    Generate the Microsoft Entra ID authorization URL.
    The PWA redirects the user to this URL to begin the OAuth2 flow.
    """
    app = get_msal_app()
    auth_url = app.get_authorization_request_url(
        scopes=ENTRA_SCOPES,
        redirect_uri=ENTRA_REDIRECT_URI,
        state=state
    )
    return auth_url

# ── Step 2: Exchange auth code for tokens ─────────────────────────────────────
def exchange_code_for_token(code: str) -> dict:
    """
    Exchange the authorization code returned by Microsoft for an access token.
    Called by the /auth/callback endpoint after Microsoft redirects back.
    """
    app = get_msal_app()
    result = app.acquire_token_by_authorization_code(
        code=code,
        scopes=ENTRA_SCOPES,
        redirect_uri=ENTRA_REDIRECT_URI
    )

    if "error" in result:
        logger.error(f"Token exchange failed: {result.get('error_description')}")
        raise HTTPException(status_code=401, detail="Authentication failed")

    return result

# ── Step 3: Get user profile and validate group membership ────────────────────
def get_user_profile(access_token: str) -> dict:
    """
    Use the Microsoft Graph API to retrieve user profile and group memberships.
    Enforces zoey_users group membership.
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        with httpx.Client(timeout=10.0) as client:
            # Get user profile
            profile_resp = client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers=headers
            )
            profile_resp.raise_for_status()
            profile = profile_resp.json()

            # Get group memberships
            groups_resp = client.get(
                "https://graph.microsoft.com/v1.0/me/memberOf",
                headers=headers
            )
            groups_resp.raise_for_status()
            groups_data = groups_resp.json()

    except httpx.HTTPError as e:
        logger.error(f"Graph API error: {e}")
        raise HTTPException(status_code=503, detail="Could not retrieve user profile")

    # Build group name list
    group_names = [
        g.get("displayName", "").lower()
        for g in groups_data.get("value", [])
        if g.get("@odata.type") == "#microsoft.graph.group"
    ]

    user = {
        "username":     profile.get("userPrincipalName", "").split("@")[0],
        "upn":          profile.get("userPrincipalName", ""),
        "display_name": profile.get("displayName", ""),
        "email":        profile.get("mail") or profile.get("userPrincipalName", ""),
        "department":   profile.get("department", ""),
        "title":        profile.get("jobTitle", ""),
        "groups":       group_names
    }

    logger.info(f"User profile retrieved: {user['display_name']} ({user['upn']})")

    # Enforce zoey_users group membership
    if ZOEY_AD_GROUP.lower() not in group_names:
        logger.warning(
            f"Access denied for {user['upn']} — not a member of '{ZOEY_AD_GROUP}'"
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied — your account is not authorized for Zoey"
        )

    logger.info(f"Access granted: {user['display_name']} ({user['upn']})")
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
        "exp":          datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_H)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    FastAPI dependency — validates Bearer token on protected routes.
    Returns decoded payload (user info) on success.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired — please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
