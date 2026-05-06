import ldap
import jwt
import os
import logging
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("zoey.auth")

# ── Config ─────────────────────────────────────────────────────────────────────
LDAP_SERVER     = os.environ.get("LDAP_SERVER",     "ldap://10.242.1.5")
LDAP_DOMAIN     = os.environ.get("LDAP_DOMAIN",     "GRAYSTONE")
LDAP_BASE_DN    = os.environ.get("LDAP_BASE_DN",    "DC=graystone,DC=solutions")
LDAP_ADMIN_DN   = os.environ.get("LDAP_ADMIN_DN",   "CN=LDAPAuth,CN=Users,DC=graystone,DC=solutions")
LDAP_ADMIN_PASS = os.environ.get("LDAP_ADMIN_PASSWORD", "")
ZOEY_AD_GROUP   = os.environ.get("ZOEY_AD_GROUP",   "zoey_users")
JWT_SECRET      = os.environ.get("JWT_SECRET",      "change_this_secret_in_env")
JWT_ALGORITHM   = "HS256"
JWT_EXPIRY_H    = int(os.environ.get("JWT_EXPIRY_HOURS", "8"))

security = HTTPBearer()

# ── Helpers ────────────────────────────────────────────────────────────────────
def decode_attr(attrs: dict, key: str) -> str:
    """Safely decode a bytes LDAP attribute to a string."""
    val = attrs.get(key, [b""])
    if isinstance(val, list):
        return val[0].decode("utf-8") if val else ""
    return val.decode("utf-8") if isinstance(val, bytes) else str(val)

def get_ldap_connection() -> ldap.ldapobject.LDAPObject:
    """Initialize and return a configured LDAP connection."""
    conn = ldap.initialize(LDAP_SERVER)
    conn.set_option(ldap.OPT_NETWORK_TIMEOUT, 5)
    conn.set_option(ldap.OPT_TIMEOUT, 5)
    conn.set_option(ldap.OPT_REFERRALS, 0)
    conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
    return conn

# ── Group Membership Check ─────────────────────────────────────────────────────
def is_zoey_user(groups: list) -> bool:
    """
    Check if the user is a member of the required AD group.
    Compares against the CN portion of each group's distinguished name.
    Example DN: CN=zoey_users,OU=Groups,DC=graystone,DC=solutions
    """
    for group in groups:
        cn = group.split(',')[0].lower()
        if cn == f"cn={ZOEY_AD_GROUP.lower()}":
            return True
    return False

# ── LDAP Authentication ────────────────────────────────────────────────────────
def authenticate_ldap(username: str, password: str) -> dict:
    """
    Authenticate a user against Active Directory using a service account bind.

    Flow:
    1. Bind as LDAPAuth service account
    2. Search for user by userPrincipalName (username@graystone.solutions)
    3. Rebind as the user to validate their password
    4. Pull user attributes
    5. Enforce zoey_users group membership
    6. Return user info dict on success

    Raises HTTPException on any failure.
    """
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")

    # Normalize — accept bare username or full UPN
    if "@" not in username:
        upn = f"{username}@graystone.solutions"
    else:
        upn = username.lower()

    # ── Step 1: Bind as service account ───────────────────────────────────────
    try:
        conn = get_ldap_connection()
        conn.simple_bind_s(LDAP_ADMIN_DN, LDAP_ADMIN_PASS)
        logger.info("LDAPAuth service account bind successful")
    except ldap.INVALID_CREDENTIALS:
        logger.error("LDAPAuth service account credentials are invalid")
        raise HTTPException(status_code=503, detail="Authentication service misconfigured")
    except ldap.SERVER_DOWN:
        logger.error(f"LDAP server unreachable at {LDAP_SERVER}")
        raise HTTPException(status_code=503, detail="Authentication server unavailable")
    except ldap.LDAPError as e:
        logger.error(f"LDAP service account bind error: {e}")
        raise HTTPException(status_code=503, detail="Authentication error")

    # ── Step 2: Search for user by UPN ────────────────────────────────────────
    try:
        search_filter = f"(userPrincipalName={upn})"
        attributes = [
            "distinguishedName",
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

        if not results:
            logger.warning(f"User not found in directory: {upn}")
            raise HTTPException(status_code=401, detail="Invalid username or password")

        user_dn, attrs = results[0]
        logger.info(f"User found in directory: {user_dn}")

    except HTTPException:
        raise
    except ldap.LDAPError as e:
        logger.error(f"LDAP search error: {e}")
        raise HTTPException(status_code=503, detail="Authentication error")
    finally:
        conn.unbind_s()

    # ── Step 3: Rebind as user to validate password ───────────────────────────
    try:
        user_conn = get_ldap_connection()
        user_conn.simple_bind_s(upn, password)
        user_conn.unbind_s()
        logger.info(f"User password validated: {upn}")
    except ldap.INVALID_CREDENTIALS:
        logger.warning(f"Invalid credentials for {upn}")
        raise HTTPException(status_code=401, detail="Invalid username or password")
    except ldap.SERVER_DOWN:
        logger.error(f"LDAP server unreachable at {LDAP_SERVER}")
        raise HTTPException(status_code=503, detail="Authentication server unavailable")
    except ldap.LDAPError as e:
        logger.error(f"LDAP user bind error: {e}")
        raise HTTPException(status_code=503, detail="Authentication error")

    # ── Step 4: Build user info dict ──────────────────────────────────────────
    user = {
        "username":     decode_attr(attrs, "sAMAccountName"),
        "upn":          upn,
        "display_name": decode_attr(attrs, "displayName"),
        "email":        decode_attr(attrs, "mail") or upn,
        "department":   decode_attr(attrs, "department"),
        "title":        decode_attr(attrs, "title"),
        "groups":       [g.decode("utf-8") for g in attrs.get("memberOf", [])]
    }

    logger.info(f"User attributes retrieved: {user['display_name']} ({user['username']})")

    # ── Step 5: Enforce zoey_users group membership ───────────────────────────
    if not is_zoey_user(user["groups"]):
        logger.warning(
            f"Access denied for {upn} — not a member of '{ZOEY_AD_GROUP}'"
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied — your account is not authorized for Zoey"
        )

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
