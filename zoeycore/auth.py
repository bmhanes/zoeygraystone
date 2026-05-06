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
ENTRA_TENANT_ID   = os.environ.get("ENTRA_TENANT_ID",   "")
ENTRA_CLIENT_ID   = os.environ.get("ENTRA_CLIENT_ID",   "")
ENTRA_CLIENT_SECRET = os.environ.get("ENTRA_CLIENT_SECRET", "")
ENTRA_AUTHORITY   = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}"
ENTRA_SCOPE       = ["https://graph.microsoft.com/.default"]
ZOEY_AD_GROUP     = os.environ.get("ZOEY_AD_GROUP", "zoey_users")

# ── JWT Config ─────────────────────────────────────────────────────────────────
JWT_SECRET    = os.environ.get("JWT_SECRET",      "change_this_secret_in_env")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_H  = int(os.environ.get("JWT_EXPIRY_HOURS", "8"))

security = HTTPBearer()

# ── MSAL Confidential Client ───────────────────────────────────────────────────
def get_msal_app():
    return msal.ConfidentialClientApplication(
        client_id=ENTRA_CLIENT_ID,
        client_credential=ENTRA_CLIENT_SECRET,
        authority=ENTRA_AUTHORITY
    )

# ── Get Graph API token (service account equivalent) ──────────────────────────
def get_graph_token() -> str:
    """Acquire a token for Microsoft Graph API using client credentials."""
    app = get_msal_app()
    result = app.acquire_token_silent(ENTRA_SCOPE, account=None)
    if not result:
        result = app.acquire_token_for_client(scopes=ENTRA_SCOPE)
    if "access_token" not in result:
        logger.error(f"Failed to acquire Graph token: {result.get('error_description')}")
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    return result["access_token"]

# ── Validate user credentials via ROPC flow ────────────────────────────────────
def authenticate_entra(username: str, password: str) -> dict:
    """
    Authenticate a user against Entra ID using Resource Owner Password Credentials.
    
    Flow:
    1. Authenticate user credentials via ROPC
    2. Acquire Graph API token via client credentials
    3. Look up user profile and group memberships
    4. Enforce zoey_users group membership
    5. Return user info dict on success
    
    Note: ROPC requires the Entra ID app to have ROPC enabled and
    'Allow public client flows' turned on in the app registration.
    """
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")

    # Normalize UPN
    if "@" not in username:
        upn = f"{username}@graystone.solutions"
    else:
        upn = username.lower()

    # ── Step 1: Authenticate user via ROPC ────────────────────────────────────
    try:
        app = get_msal_app()
        result = app.acquire_token_by_username_password(
            username=upn,
            password=password,
            scopes=["https://graph.microsoft.com/User.Read",
                    "https://graph.microsoft.com/GroupMember.Read.All"]
        )

        if "error" in result:
            error = result.get("error")
            desc  = result.get("error_description", "")
            logger.warning(f"Auth failed for {upn}: {error} — {desc}")

            if "AADSTS50126" in desc:
                raise HTTPException(status_code=401, detail="Invalid username or password")
            elif "AADSTS50057" in desc:
                raise HTTPException(status_code=401, detail="Account is disabled")
            elif "AADSTS50076" in desc:
                raise HTTPException(status_code=401, detail="MFA required — use the web login flow")
            else:
                raise HTTPException(status_code=401, detail="Authentication failed")

        user_token = result["access_token"]
        logger.info(f"ROPC authentication successful for {upn}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MSAL error: {e}")
        raise HTTPException(status_code=503, detail="Authentication service error")

    # ── Step 2: Get user profile from Graph API ───────────────────────────────
    try:
        headers = {"Authorization": f"Bearer {user_token}"}

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

    # ── Step 3: Build user dict ───────────────────────────────────────────────
    group_names = [
        g.get("displayName", "").lower()
        for g in groups_data.get("value", [])
        if g.get("@odata.type") == "#microsoft.graph.group"
    ]

    user = {
        "username":     profile.get("userPrincipalName", upn).split("@")[0],
        "upn":          profile.get("userPrincipalName", upn),
        "display_name": profile.get("displayName", upn),
        "email":        profile.get("mail") or profile.get("userPrincipalName", upn),
        "department":   profile.get("department", ""),
        "title":        profile.get("jobTitle", ""),
        "groups":       group_names
    }

    logger.info(f"User profile retrieved: {user['display_name']} ({user['upn']})")

    # ── Step 4: Enforce zoey_users group membership ───────────────────────────
    if ZOEY_AD_GROUP.lower() not in group_names:
        logger.warning(
            f"Access denied for {upn} — not a member of '{ZOEY_AD_GROUP}'"
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