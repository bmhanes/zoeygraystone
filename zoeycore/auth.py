import msal
import jwt
import os
import logging
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("zoey.auth")

# ── Scopes ─────────────────────────────────────────────────────────────────────
SCOPES = [
    "User.Read",
    "GroupMember.Read.All"
]

ZOEY_AD_GROUP = os.environ.get("ZOEY_AD_GROUP", "zoey_users")

# ── Access gate groups — any member of these may log in ───────────────────────
ACCESS_GROUPS = {
    g.strip().lower()
    for g in os.environ.get(
        "ZOEY_ACCESS_GROUPS",
        "zoey_users,zoey_admin,gss_users,gss_premium,gss_blue,zoey_dev_consultants,zoey_prod_users,zoey_prod_premium"
    ).split(",")
    if g.strip()
}

# ── JWT Config ─────────────────────────────────────────────────────────────────
JWT_SECRET    = os.environ.get("JWT_SECRET",      "change_this_secret_in_env")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_H  = int(os.environ.get("JWT_EXPIRY_HOURS", "8"))

security = HTTPBearer()

# ── MSAL Confidential Client ───────────────────────────────────────────────────
def _msal_app() -> msal.ConfidentialClientApplication:
    tenant_id     = os.environ.get("AZURE_TENANT_ID", "")
    client_id     = os.environ.get("AZURE_CLIENT_ID", "")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET", "")
    authority     = f"https://login.microsoftonline.com/{tenant_id}"
    
    return msal.ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret,
    )

# ── Step 1: Generate Microsoft login URL ──────────────────────────────────────
def get_auth_url() -> str:
    redirect_uri = os.environ.get("AZURE_REDIRECT_URI", "http://localhost:8000/auth/callback")
    return _msal_app().get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )

# ── Step 2: Exchange auth code for tokens ─────────────────────────────────────
def exchange_code_for_token(code: str) -> dict:
    """
    Exchange the authorization code returned by Microsoft for an access token.
    Called by the /auth/callback endpoint after Microsoft redirects back.
    """
    app = _msal_app()
    result = app.acquire_token_by_authorization_code(
        code=code,
        scopes=SCOPES,  # ← was ENTRA_SCOPES
        redirect_uri=os.environ.get("AZURE_REDIRECT_URI", "http://localhost:8000/auth/callback")
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

    # Enforce group membership — user must belong to at least one access group
    if not any(g in ACCESS_GROUPS for g in group_names):
        logger.warning(
            f"Access denied for {user['upn']} — not a member of any authorized group"
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
        "groups":       user.get("groups", []),
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
