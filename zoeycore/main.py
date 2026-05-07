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

# ── DB ─────────────────────────────────────────────────────────────────────────
db = None

# ── System Prompt ──────────────────────────────────────────────────────────────
ZOEY_SYSTEM_PROMPT = """You are Zoey Graystone, an intelligent AI assistant built for
Graystone Solutions. You are helpful, professional, and security-minded.
You assist with research, tooling, and general life tasks.
Be concise but thorough. If you are unsure about something, say so.
Always prioritize user privacy and data security.
You will be told who you are speaking with at the start of each session.
Use their name naturally and remember context about them."""

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
    """Redirect to Microsoft logout."""
    tenant_id = os.environ.get("ENTRA_TENANT_ID", "")
    logout_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/logout?post_logout_redirect_uri=/"
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

    # ── Route to correct model ─────────────────────────────────────────────────
    try:
        if req.mode == "advanced":
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
