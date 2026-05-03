import ldap
import jwt
import os
import logging
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("zoey.auth")

# ── Config ─────────────────────────────────────────────────────────────────────
LDAP_SERVER   = os.environ.get("LDAP_SERVER",   "ldap://10.242.1.5")
LDAP_DOMAIN   = os.environ.get("LDAP_DOMAIN",   "GRAYSTONE")
LDAP_BASE_DN  = os.environ.get("LDAP_BASE_DN",  "DC=GRAYSTONE,DC=local")
ZOEY_AD_GROUP = os.environ.get("ZOEY_AD_GROUP", "Zoey_Users")
JWT_SECRET    = os.environ.get("JWT_SECRET",     "change_this_secret_in_env")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_H  = int(os.environ.get("JWT_EXPIRY_HOURS", "8"))

security = HTTPBearer()

# ── Group Membership Check ─────────────────────────────────────────────────────
def is_zoey_user(groups: list) -> bool:
    """
    Check if the user is a member of the required AD group.
    Compares against the CN portion of each group's distinguished name.
    Example DN: CN=Zoey Users,OU=Groups,DC=GRAYSTONE,DC=local
    """
    for group in groups:
        cn = group.split(',')[0].lower()  # grab just the CN portion
        if cn == f"cn={ZOEY_AD_GROUP.lower()}":
            return True
    return False

# ── LDAP Authentication ────────────────────────────────────────────────────────
def authenticate_ldap(username: str, password: str) -> dict:
    """
    Authenticate a user against GSN01 Active Directory via LDAP.
    Validates credentials, pulls user attributes, and enforces
    membership in the Zoey Users AD group.
    Returns user info dict on success, raises HTTPException on failure.
    """
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")

    # Bind DN format for Windows AD: DOMAIN\\username
    bind_dn = f"{LDAP_DOMAIN}\\{username}"

    try:
        conn = ldap.initialize(LDAP_SERVER)
        conn.set_option(ldap.OPT_NETWORK_TIMEOUT, 5)
        conn.set_option(ldap.OPT_TIMEOUT, 5)
        conn.set_option(ldap.OPT_REFERRALS, 0)

        # Attempt bind — this validates credentials
        conn.simple_bind_s(bind_dn, password)
        logger.info(f"LDAP bind successful for {username}")

        # Search for user attributes
        search_filter = f"(sAMAccountName={username})"
        attributes = [
            "sAMAccountName",
            "displayName",
            "mail",
            "memberOf",
            "department",
            "title"
        ]

        results = conn.search_s(
            LDAP_BASE_DN,
            ldap.SCOPE_SUBTREE,
            search_filter,
            attributes
        )

        conn.unbind_s()

        if not results:
            raise HTTPException(status_code=401, detail="User not found in directory")

        _, attrs = results[0]

        # Decode bytes from LDAP response
        def decode(val):
            if isinstance(val, list):
                return val[0].decode("utf-8") if val else ""
            return val.decode("utf-8") if isinstance(val, bytes) else val

        user = {
            "username":     decode(attrs.get("sAMAccountName", [""])),
            "display_name": decode(attrs.get("displayName", [""])),
            "email":        decode(attrs.get("mail", [""])),
            "department":   decode(attrs.get("department", [""])),
            "title":        decode(attrs.get("title", [""])),
            "groups":       [g.decode("utf-8") for g in attrs.get("memberOf", [])]
        }

        logger.info(f"LDAP attributes retrieved for {user['display_name']} ({user['username']})")

        # ── Zoey Access Control ────────────────────────────────────────────────
        if not is_zoey_user(user["groups"]):
            logger.warning(
                f"Access denied for {username} — not a member of '{ZOEY_AD_GROUP}'"
            )
            raise HTTPException(
                status_code=403,
                detail="Access denied — your account is not authorized for Zoey"
            )

        logger.info(f"Access granted: {user['display_name']} ({user['username']})")
        return user

    except ldap.INVALID_CREDENTIALS:
        logger.warning(f"Invalid credentials for {username}")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    except ldap.SERVER_DOWN:
        logger.error(f"LDAP server unreachable at {LDAP_SERVER}")
        raise HTTPException(status_code=503, detail="Authentication server unavailable")

    except ldap.LDAPError as e:
        logger.error(f"LDAP error: {e}")
        raise HTTPException(status_code=503, detail="Authentication error")


# ── JWT Token ──────────────────────────────────────────────────────────────────
def create_jwt(user: dict) -> str:
    """Issue a signed JWT for an authenticated user."""
    payload = {
        "sub":          user["username"],
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
