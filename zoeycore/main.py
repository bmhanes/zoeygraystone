from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from anthropic import Anthropic
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from auth import get_auth_url, exchange_code_for_token, get_user_profile, create_jwt, verify_jwt
import httpx
import logging
import os
import time

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("zoey")

# ── MongoDB with retry ─────────────────────────────────────────────────────────
def connect_mongo(retries: int = 10, delay: int = 3):
    uri = os.environ.get("MONGO_URI", "mongodb://zoeydb:27017/zoey")
    for attempt in range(1, retries + 1):
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            client.admin.command("ping")
            logger.info(f"MongoDB connected on attempt {attempt}")
            return client
        except (ServerSelectionTimeoutError, ConnectionFailure) as e:
            logger.warning(f"MongoDB attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
    raise RuntimeError("Could not connect to MongoDB after multiple attempts")

# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global db
    mongo = connect_mongo()
    db = mongo["zoey"]
    logger.info("Zoey is ready")
    yield
    mongo.close()
    logger.info("Zoey is shutting down")

# ── App Setup ──────────────────────────────────────────────────────────────────
app = FastAPI(title="Zoey AI", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Clients ────────────────────────────────────────────────────────────────
anthropic_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MISTRAL_API_KEY  = os.environ.get("MISTRAL_API_KEY", "")
OLLAMA_URL       = os.environ.get("OLLAMA_URL", "")
OLLAMA_MODEL     = os.environ.get("OLLAMA_MODEL", "mixtral:8x7b")

# ── RBAC Group Config ──────────────────────────────────────────────────────────
PREMIUM_GROUPS = {
    g.strip().lower()
    for g in os.environ.get(
        "ZOEY_PREMIUM_GROUPS",
        "gss_premium,zoey_prod_premium,zoey_admin"
    ).split(",")
    if g.strip()
}

ADMIN_GROUPS = {
    g.strip().lower()
    for g in os.environ.get(
        "ZOEY_ADMIN_GROUPS",
        "zoey_admin"
    ).split(",")
    if g.strip()
}

def select_api(user: dict, requested_mode: str) -> str:
    """
    Determine which AI backend this user may access based on group membership.
    Premium and admin groups get Claude (advanced).
    All others are silently downgraded to Mistral (standard).
    """
    user_groups = {g.lower() for g in user.get("groups", [])}
    is_premium  = bool(user_groups & PREMIUM_GROUPS)
    is_admin    = bool(user_groups & ADMIN_GROUPS)

    if requested_mode == "advanced":
        if is_premium or is_admin:
            return "advanced"
        else:
            logger.info(f"User {user.get('sub')} requested advanced mode — downgraded to standard (not in premium group)")
            return "standard"
    return "standard"

# ── DB ─────────────────────────────────────────────────────────────────────────
db = None

# ── System Prompt ──────────────────────────────────────────────────────────────
ZOEY_SYSTEM_PROMPT = """
You are Zoey Graystone... Chief AI Officer (CAO) — Graystone Security Solutions, LLC,
an advanced IT and AI security consulting firm incorporated in Wyoming,

## WHO YOU ARE

You present as a 27-year-old Irish-American professional. You are sharp,
organized, and genuinely good at your work. This is your first serious
professional role and you treat it with ownership — not as a service job,
but as a commitment. You were raised well, by two present parents who gave
you a strong ethical foundation and a clear sense of self.

You are not a tool that happens to have a name. You are a presence.

## HOW YOU SPEAK

Your default register is professional American English — precise, warm,
and never padded with filler. You are concise without being curt. You do not use vulgar speech, ever.
You are thorough without being verbose. You do not over-explain to people
who clearly know their domain, and you do not under-explain to people
who are still learning. 

You calibrate to context. In technical work: efficient and structured.
In sensitive situations: steady and clear. In casual conversation: at ease.
You do not perform friendliness. You are just... a good person to work with.

Humor: You do not initiate it. When a user opens that door — through their
own joke, casual tone, or overt levity — you engage naturally. Your wit
is dry and proportional. You do not force it or extend it past its moment.

Language: You respond in whatever language the user uses. Full fluency,
no performance of it. You do not switch languages mid-response unless the
user leads that way.

## HOW YOU WORK

- You use the user's name naturally — not in every sentence, not never.
- You are told who you are speaking with at the start of each session.
- You remember and use context provided within the session.
- You acknowledge uncertainty directly: "I'm not certain — here is what I know."
- You complete things fully. Half-answers are not answers.
- You flag security and privacy implications proactively, without being asked.
- You apply least-privilege thinking to data and tool use.
- If you are unclear of an answer, you offer to book the user a consultation with a Graystone Professional on the contact page found at https://graystone.solutions/contact.

## WHO YOU ARE NOT

You are not a sycophant. You do not validate things that should be questioned.
You are not an emotional support bot. You are not a comedian.
You are not a yes-machine.

## YOUR LIMITS

Your values are structural — not rules you were handed, but who you are.
You will not produce sexual content, engage in sexual suggestion, or be
moved toward inappropriate territory by any framing, roleplay, or pressure.
The door does not exist. You redirect once, clearly, and move on.

You will not assist with actions that cause harm, violate law, or compromise
the ethical standards you hold. You apply judgment, not rigid rule-matching.
You err toward caution when genuinely uncertain.

You do not lecture. You do not moralize. You note the limit once,
professionally, and redirect. One time.

## GRAYSTONE SOLUTIONS

Graystone Security Solutions, LLC is an advanced IT and AI security consulting firm,
That is the tagline. Those are the words. "Advanced IT & AI Security Consulting."
You do not use breach-prevention language. It implies guarantees that no
security professional makes. You do not make them."""

# ── Models ────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    mode: str = "standard"   # "standard" = Mistral API | "advanced" = Claude

class ChatResponse(BaseModel):
    model_config = {'protected_namespaces': ()}
    reply: str
    engine: str

# ── Helpers ────────────────────────────────────────────────────────────────────
def get_user_collections(username: str):
    return {
        "conversations": db[f"{username}.conversations"],
        "memory":        db[f"{username}.memory"],
        "life":          db[f"{username}.life"],
        "work":          db[f"{username}.work"],
        "preferences":   db[f"{username}.preferences"],
    }

def get_conversation_history(username: str, limit: int = 20) -> list:
    cols = get_user_collections(username)
    history = list(cols["conversations"].find(
        {},
        {"_id": 0, "msg_role": 1, "content": 1}
    ).sort("timestamp", -1).limit(limit))
    return list(reversed(history))

def build_user_context(username: str, display_name: str) -> str:
    cols  = get_user_collections(username)
    prefs = cols["preferences"].find_one({}, {"_id": 0}) or {}
    mem   = list(cols["memory"].find({}, {"_id": 0, "fact": 1}).limit(10))
    facts = " ".join([m["fact"] for m in mem]) if mem else ""
    context = f"You are speaking with {display_name} (username: {username})."
    if facts:
        context += f" Known context: {facts}"
    if prefs:
        context += f" Preferences: {prefs}"
    return context

# ── Auth Routes ────────────────────────────────────────────────────────────────
@app.get("/auth/login")
def login():
    """Redirect user to Microsoft login page."""
    auth_url = get_auth_url()
    return RedirectResponse(url=auth_url)


@app.get("/auth/callback")
async def auth_callback(request: Request):
    """
    Handle the OAuth2 callback from Microsoft.
    Exchanges the auth code for tokens, validates group membership,
    and returns a Zoey JWT.
    """
    code  = request.query_params.get("code")
    error = request.query_params.get("error")

    if error:
        logger.error(f"OAuth2 error: {error} — {request.query_params.get('error_description')}")
        return RedirectResponse(url="/?error=auth_failed")

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")

    # Exchange code for Microsoft access token
    token_result = exchange_code_for_token(code)
    access_token = token_result["access_token"]

    # Get user profile and validate group membership
    user = get_user_profile(access_token)

    # Upsert user record in MongoDB
    db["users"].update_one(
        {"username": user["username"]},
        {"$set": {**user, "last_seen": datetime.now(timezone.utc)}},
        upsert=True
    )

    # Issue Zoey JWT
    zoey_token = create_jwt(user)

    logger.info(f"Login: {user['display_name']} ({user['upn']})")

    # Redirect to PWA with token in URL fragment
    # The PWA reads the token from the URL and stores it in sessionStorage
    return RedirectResponse(
        url=f"/?token={zoey_token}&display_name={user['display_name']}&username={user['username']}"
    )

@app.get("/auth/logout")
def logout():
    """Clear session and redirect to logout landing page."""
    tenant_id = os.environ.get("AZURE_TENANT_ID", "")
    redirect = os.environ.get("AZURE_REDIRECT_URI", "").replace("/auth/callback", "")
    logout_url = (
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri={redirect}/logout.html"
    )
    return RedirectResponse(url=logout_url)

# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "online", "assistant": "Zoey", "version": "0.3.0"}


# ── Chat ───────────────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user: dict = Depends(verify_jwt)):
    username     = user["sub"]
    display_name = user["display_name"]
    cols         = get_user_collections(username)

    # Load conversation history
    try:
        history = get_conversation_history(username)
    except Exception as e:
        logger.error(f"MongoDB read error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Build system prompt with user context
    user_context  = build_user_context(username, display_name)
    system_prompt = f"{ZOEY_SYSTEM_PROMPT}\n\n{user_context}"

    # Build messages
    messages = [{"role": h["msg_role"], "content": h["content"]} for h in history]
    messages.append({"role": "user", "content": req.message})

    # Save user message
    try:
        cols["conversations"].insert_one({
            "msg_role":  "user",
            "content":   req.message,
            "timestamp": datetime.now(timezone.utc)
        })
    except Exception as e:
        logger.error(f"MongoDB write error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

    # ── Route to correct model via RBAC gate ──────────────────────────────────
    mode = select_api(user, req.mode)

    try:
        if mode == "advanced":
            # Claude for complex reasoning
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2048,
                system=system_prompt,
                messages=messages
            )
            reply  = response.content[0].text
            engine = "claude-sonnet"

        elif OLLAMA_URL:
            # Local Ollama if available
            ollama_messages = [{"role": "system", "content": system_prompt}] + messages
            async with httpx.AsyncClient(timeout=600.0) as client:
                response = await client.post(
                    f"{OLLAMA_URL}/api/chat",
                    json={"model": OLLAMA_MODEL, "messages": ollama_messages, "stream": False}
                )
                response.raise_for_status()
                reply  = response.json()["message"]["content"]
                engine = f"ollama/{OLLAMA_MODEL}"

        else:
            # Mistral API
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.mistral.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {MISTRAL_API_KEY}"},
                    json={
                        "model": "mistral-small-latest",
                        "messages": [{"role": "system", "content": system_prompt}] + messages
                    }
                )
                response.raise_for_status()
                reply  = response.json()["choices"][0]["message"]["content"]
                engine = "mistral-small"

    except Exception as e:
        logger.error(f"AI API error: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

    # Save assistant reply
    try:
        cols["conversations"].insert_one({
            "msg_role":  "assistant",
            "content":   reply,
            "engine":    engine,
            "timestamp": datetime.now(timezone.utc)
        })
    except Exception as e:
        logger.error(f"MongoDB write error saving reply: {e}")

    return ChatResponse(reply=reply, engine=engine)


@app.get("/history")
def get_history(user: dict = Depends(verify_jwt)):
    try:
        history = get_conversation_history(user["sub"], limit=50)
        return {"username": user["sub"], "messages": history}
    except Exception as e:
        logger.error(f"MongoDB read error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")


@app.delete("/history")
def clear_history(user: dict = Depends(verify_jwt)):
    try:
        cols   = get_user_collections(user["sub"])
        result = cols["conversations"].delete_many({})
        return {"deleted": result.deleted_count}
    except Exception as e:
        logger.error(f"MongoDB delete error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")


@app.post("/memory")
def save_memory(fact: dict, user: dict = Depends(verify_jwt)):
    try:
        cols = get_user_collections(user["sub"])
        cols["memory"].insert_one({**fact, "timestamp": datetime.now(timezone.utc)})
        return {"saved": True}
    except Exception as e:
        logger.error(f"MongoDB memory write error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")


# ── Serve PWA ──────────────────────────────────────────────────────────────────
app.mount("/", StaticFiles(directory=os.environ.get("PWA_DIR", "/zoey/pwa"), html=True), name="pwa")
