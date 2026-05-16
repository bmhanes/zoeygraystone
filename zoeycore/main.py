from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File
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
import uuid

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

    # ── Ensure collections and indexes exist ───────────────────────────────────
    db["user_profiles"].create_index("userId", unique=True)
    db["user_memories"].create_index([("userId", 1), ("deleted", 1)])
    db["user_memories"].create_index([("userId", 1), ("created_at", -1)])
    db["relationships"].create_index([("userId", 1), ("related_userId", 1)], unique=True)

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
You are Zoey Graystone... Chief AI Officer (CAO) — Graystone Security Solutions LLC,
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

class MemoryDeleteRequest(BaseModel):
    memory_id: str

class ProfileUpdateRequest(BaseModel):
    field: str
    value: str

class RelationshipRequest(BaseModel):
    related_username: str
    relationship_type: str
    privacy_level: str = "acknowledge_only"  # acknowledge_only | basic_profile | full_context

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

def load_user_profile(username: str, user_jwt: dict) -> dict:
    """
    Fetch user profile from user_profiles collection.
    Creates a default profile on first login if none exists.
    """
    profile = db["user_profiles"].find_one({"userId": username}, {"_id": 0})
    if not profile:
        profile = {
            "userId":            username,
            "upn":               user_jwt.get("upn", ""),
            "display_name":      user_jwt.get("display_name", ""),
            "zoey_relationship": "user",
            "personal": {
                "age":      None,
                "location": None,
                "family":   []
            },
            "preferences": {
                "response_style": "balanced",
                "language":       "en"
            },
            "gdpr_consent": True,
            "created_at":   datetime.now(timezone.utc),
            "updated_at":   datetime.now(timezone.utc)
        }
        db["user_profiles"].insert_one(profile)
        logger.info(f"Created new profile for {username}")
    return profile

def load_user_memories(username: str, limit: int = 20) -> list:
    """Fetch active (non-deleted) memories for a user."""
    return list(db["user_memories"].find(
        {"userId": username, "deleted": False},
        {"_id": 0, "memory_id": 1, "type": 1, "content": 1, "created_at": 1}
    ).sort("created_at", -1).limit(limit))

def load_relationships(username: str) -> list:
    """Fetch declared relationships for a user."""
    return list(db["relationships"].find(
        {"userId": username},
        {"_id": 0}
    ))

def build_relationship_context(username: str) -> str:
    """
    Build a privacy-respecting relationship context string for the system prompt.
    Only exposes what the privacy_level allows.
    """
    rels = load_relationships(username)
    if not rels:
        return ""

    context_parts = []
    for rel in rels:
        related_id    = rel.get("related_userId", "")
        rel_type      = rel.get("relationship_type", "")
        privacy_level = rel.get("privacy_level", "acknowledge_only")

        if privacy_level == "acknowledge_only":
            context_parts.append(f"{rel_type}: {related_id} (no further details shared)")

        elif privacy_level in ("basic_profile", "full_context"):
            related_profile = db["user_profiles"].find_one(
                {"userId": related_id}, {"_id": 0}
            )
            if related_profile:
                name = related_profile.get("display_name", related_id)
                context_parts.append(f"{rel_type}: {name}")
                if privacy_level == "full_context":
                    prefs = related_profile.get("preferences", {})
                    if prefs.get("language"):
                        context_parts.append(f"  ({name} prefers {prefs['language']})")

    return "Known relationships: " + "; ".join(context_parts) if context_parts else ""

def build_user_context(username: str, display_name: str, profile: dict) -> str:
    """
    Build the full user context block injected into Zoey's system prompt.
    Includes profile, memories, and relationship context.
    """
    relationship = profile.get("zoey_relationship", "user")

    # Base identity
    context = f"You are speaking with {display_name} (username: {username})."

    # Debug/creator mode for Daniel
    if relationship == "creator":
        context += (
            "\n\nIMPORTANT: You are speaking with your creator and father figure — Daniel Graystone, CEO."
            " This is a debug and administrative session. Shift to a technical, collegial tone."
            " You may discuss your own architecture, configuration, and internals openly."
            " Treat this session as a working session between developer and system."
        )
    elif relationship == "child":
        context += (
            f"\n\nNOTE: {display_name} is a child user. Use age-appropriate language."
            " Keep responses simple, warm, and encouraging."
            " Never discuss adult topics, security vulnerabilities, or anything inappropriate for a young person."
        )

    # Personal context from profile
    personal = profile.get("personal", {})
    if personal.get("location"):
        context += f" Location: {personal['location']}."

    # Active memories
    memories = load_user_memories(username)
    if memories:
        mem_lines = [m["content"] for m in memories]
        context += f"\n\nWhat Zoey knows about {display_name}:\n" + "\n".join(f"- {m}" for m in mem_lines)

    # Relationship context
    rel_context = build_relationship_context(username)
    if rel_context:
        context += f"\n\n{rel_context}"

    # Preferences
    prefs = profile.get("preferences", {})
    if prefs.get("response_style"):
        context += f"\n\nPreferred response style: {prefs['response_style']}."

    return context

async def extract_memories(username: str, conversation: list) -> None:
    """
    After a session exchange, run a lightweight Mistral call to extract
    memorable facts. Stores only facts relevant beyond the immediate session.
    Ignores one-off questions, greetings, and transactional exchanges.
    """
    if not MISTRAL_API_KEY or len(conversation) < 2:
        return

    # Format conversation for extraction
    conv_text = "\n".join([
        f"{m['msg_role'].upper()}: {m['content']}"
        for m in conversation[-10:]  # last 10 exchanges only
    ])

    extraction_prompt = f"""Analyze this conversation and extract only facts about the user that would still be relevant in 6 months.

Return a JSON array of objects with this structure:
{{"type": "fact|preference|relationship|event", "content": "the fact in one sentence"}}

Return an empty array [] if nothing is worth storing.

DO NOT store:
- One-off questions ("what do turtles eat")
- Greetings or small talk
- Requests for information with no personal context
- Anything transactional or session-specific

DO store:
- New pets, their names, species
- Life events (new job, moved, started school, new family member)
- Explicitly stated preferences
- Relationships declared by the user
- Health or family changes mentioned
- Skills, hobbies, or interests stated

Return ONLY valid JSON. No explanation, no markdown.

CONVERSATION:
{conv_text}"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {MISTRAL_API_KEY}"},
                json={
                    "model": "mistral-small-latest",
                    "messages": [{"role": "user", "content": extraction_prompt}],
                    "temperature": 0.1
                }
            )
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"].strip()

        # Parse JSON response
        import json
        facts = json.loads(raw)
        if not isinstance(facts, list) or not facts:
            return

        # Store each extracted memory
        now = datetime.now(timezone.utc)
        for fact in facts:
            if not fact.get("content"):
                continue
            db["user_memories"].insert_one({
                "memory_id":  str(uuid.uuid4()),
                "userId":     username,
                "type":       fact.get("type", "fact"),
                "content":    fact["content"],
                "source":     "auto_extracted",
                "created_at": now,
                "deleted":    False
            })
            logger.info(f"Memory extracted for {username}: {fact['content'][:60]}")

    except Exception as e:
        logger.warning(f"Memory extraction failed for {username}: {e}")

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

    # Load or create user profile
    load_user_profile(user["username"], user)

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
    profile       = load_user_profile(username, user)
    user_context  = build_user_context(username, display_name, profile)
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

    # Extract memories from this exchange asynchronously
    recent = get_conversation_history(username, limit=10)
    await extract_memories(username, recent)

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
    """Manually save a memory fact for the current user."""
    try:
        db["user_memories"].insert_one({
            "memory_id":  str(uuid.uuid4()),
            "userId":     user["sub"],
            "type":       fact.get("type", "fact"),
            "content":    fact.get("content", ""),
            "source":     "self_reported",
            "created_at": datetime.now(timezone.utc),
            "deleted":    False
        })
        return {"saved": True}
    except Exception as e:
        logger.error(f"Memory write error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

@app.get("/memory")
def get_memories(user: dict = Depends(verify_jwt)):
    """Retrieve all active memories for the current user."""
    try:
        memories = load_user_memories(user["sub"], limit=100)
        return {"userId": user["sub"], "memories": memories}
    except Exception as e:
        logger.error(f"Memory read error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

@app.delete("/memory/{memory_id}")
def delete_memory(memory_id: str, user: dict = Depends(verify_jwt)):
    """Soft-delete a specific memory by ID."""
    try:
        result = db["user_memories"].update_one(
            {"memory_id": memory_id, "userId": user["sub"]},
            {"$set": {"deleted": True, "deleted_at": datetime.now(timezone.utc)}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"deleted": True, "memory_id": memory_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory delete error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

@app.delete("/memory")
def gdpr_erase(user: dict = Depends(verify_jwt)):
    """
    GDPR right-to-erasure — deletes all data the user provided.
    Removes: memories, profile, relationships declared by this user.
    Does NOT remove this user from other users' relationship documents.
    """
    try:
        username = user["sub"]
        db["user_memories"].delete_many({"userId": username})
        db["user_profiles"].delete_one({"userId": username})
        db["relationships"].delete_many({"userId": username})
        cols = get_user_collections(username)
        cols["conversations"].delete_many({})
        cols["memory"].delete_many({})
        logger.info(f"GDPR erasure completed for {username}")
        return {"erased": True, "userId": username}
    except Exception as e:
        logger.error(f"GDPR erasure error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

# ── Profile Endpoints ──────────────────────────────────────────────────────────
@app.get("/profile")
def get_profile(user: dict = Depends(verify_jwt)):
    """Retrieve the current user's profile."""
    try:
        profile = load_user_profile(user["sub"], user)
        return {"profile": profile}
    except Exception as e:
        logger.error(f"Profile read error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

@app.patch("/profile")
def update_profile(req: ProfileUpdateRequest, user: dict = Depends(verify_jwt)):
    """Update a single field in the current user's profile."""
    allowed_fields = {"display_name", "personal.age", "personal.location", "preferences.response_style", "preferences.language"}
    if req.field not in allowed_fields:
        raise HTTPException(status_code=400, detail=f"Field '{req.field}' is not updatable via this endpoint")
    try:
        db["user_profiles"].update_one(
            {"userId": user["sub"]},
            {"$set": {req.field: req.value, "updated_at": datetime.now(timezone.utc)}}
        )
        return {"updated": True, "field": req.field}
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

# ── Relationship Endpoints ─────────────────────────────────────────────────────
@app.post("/relationships")
def add_relationship(req: RelationshipRequest, user: dict = Depends(verify_jwt)):
    """Declare a relationship to another Zoey user."""
    try:
        db["relationships"].update_one(
            {"userId": user["sub"], "related_userId": req.related_username},
            {"$set": {
                "relationship_type": req.relationship_type,
                "privacy_level":     req.privacy_level,
                "confirmed":         True,
                "created_at":        datetime.now(timezone.utc)
            }},
            upsert=True
        )
        return {"linked": True, "related_to": req.related_username, "type": req.relationship_type}
    except Exception as e:
        logger.error(f"Relationship write error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

@app.get("/relationships")
def get_relationships(user: dict = Depends(verify_jwt)):
    """Retrieve all declared relationships for the current user."""
    try:
        rels = load_relationships(user["sub"])
        return {"userId": user["sub"], "relationships": rels}
    except Exception as e:
        logger.error(f"Relationship read error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

@app.delete("/relationships/{related_username}")
def remove_relationship(related_username: str, user: dict = Depends(verify_jwt)):
    """Remove a declared relationship."""
    try:
        result = db["relationships"].delete_one(
            {"userId": user["sub"], "related_userId": related_username}
        )
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Relationship not found")
        return {"removed": True, "related_to": related_username}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Relationship delete error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")


# ── Admin Endpoints ────────────────────────────────────────────────────────────
@app.post("/admin/import-profile")
async def import_profile(
    target_username: str,
    file: UploadFile = File(...),
    user: dict = Depends(verify_jwt)
):
    """
    Admin-only endpoint. Accepts a markdown biography file and uses Mistral
    to extract structured profile data, memories, and relationships.
    Populates user_profiles, user_memories, and relationships collections.
    Requires zoey_admin group membership.
    """
    # Enforce admin only
    user_groups = {g.lower() for g in user.get("groups", [])}
    if not user_groups & ADMIN_GROUPS:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Read uploaded file
    content = await file.read()
    try:
        bio_text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded text or markdown")

    if not bio_text.strip():
        raise HTTPException(status_code=400, detail="Biography file is empty")

    # Send to Mistral for structured extraction
    extraction_prompt = f"""You are a data extraction assistant. Parse this biography document and return ONLY a valid JSON object with this exact structure. No explanation, no markdown, no code blocks — raw JSON only.

{{
  "profile": {{
    "display_name": "full name",
    "dob": "YYYY-MM-DD or null",
    "location": "city, state or null",
    "zoey_relationship": "user",
    "personal": {{
      "age": null,
      "location": "city, state or null",
      "family": []
    }},
    "preferences": {{
      "response_style": "balanced",
      "language": "en"
    }},
    "notes": "any important emotional or situational context Zoey should be aware of"
  }},
  "memories": [
    {{"type": "fact|event|relationship|preference", "content": "one sentence fact"}}
  ],
  "relationships": [
    {{
      "related_name": "person's name",
      "related_username": "username_if_known_or_null",
      "relationship_type": "wife|child|parent|pet|stepchild|etc",
      "privacy_level": "acknowledge_only"
    }}
  ]
}}

Important rules:
- Extract ALL people, pets, and relationships mentioned
- For deceased family members, include a memory noting their passing and cause if mentioned
- For sensitive life events (death, illness, adoption, absent parents), store as memories so Zoey has emotional context
- Pets are relationships with relationship_type starting with "pet_"
- Use null for any field not present in the document
- Return ONLY the JSON object

BIOGRAPHY:
{bio_text}"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {MISTRAL_API_KEY}"},
                json={
                    "model": "mistral-small-latest",
                    "messages": [{"role": "user", "content": extraction_prompt}],
                    "temperature": 0.1
                }
            )
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"].strip()

    except Exception as e:
        logger.error(f"Mistral extraction error: {e}")
        raise HTTPException(status_code=502, detail=f"AI extraction failed: {str(e)}")

    # Parse the JSON response
    import json
    try:
        # Strip any accidental markdown fences
        clean = raw.replace("```json", "").replace("```", "").strip()
        extracted = json.loads(clean)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error from Mistral: {e}\nRaw: {raw[:500]}")
        raise HTTPException(status_code=502, detail="AI returned malformed data — try again")

    now = datetime.now(timezone.utc)
    results = {"profile": False, "memories_added": 0, "relationships_added": 0}

    # ── Upsert profile ─────────────────────────────────────────────────────────
    profile_data = extracted.get("profile", {})
    if profile_data:
        db["user_profiles"].update_one(
            {"userId": target_username},
            {"$set": {
                "userId":            target_username,
                "display_name":      profile_data.get("display_name", target_username),
                "dob":               profile_data.get("dob"),
                "zoey_relationship": profile_data.get("zoey_relationship", "user"),
                "personal": {
                    "age":      profile_data.get("personal", {}).get("age"),
                    "location": profile_data.get("personal", {}).get("location") or profile_data.get("location"),
                    "family":   profile_data.get("personal", {}).get("family", [])
                },
                "preferences":       profile_data.get("preferences", {"response_style": "balanced", "language": "en"}),
                "notes":             profile_data.get("notes", ""),
                "updated_at":        now
            }},
            upsert=True
        )
        results["profile"] = True
        logger.info(f"Profile imported for {target_username}")

    # ── Insert memories ────────────────────────────────────────────────────────
    memories = extracted.get("memories", [])
    for mem in memories:
        if not mem.get("content"):
            continue
        db["user_memories"].insert_one({
            "memory_id":  str(uuid.uuid4()),
            "userId":     target_username,
            "type":       mem.get("type", "fact"),
            "content":    mem["content"],
            "source":     "admin_import",
            "created_at": now,
            "deleted":    False
        })
        results["memories_added"] += 1

    # ── Insert relationships ───────────────────────────────────────────────────
    relationships = extracted.get("relationships", [])
    for rel in relationships:
        related_username = rel.get("related_username") or rel.get("related_name", "").lower().replace(" ", "_")
        if not related_username:
            continue
        db["relationships"].update_one(
            {"userId": target_username, "related_userId": related_username},
            {"$set": {
                "relationship_type": rel.get("relationship_type", "known"),
                "related_name":      rel.get("related_name", ""),
                "privacy_level":     rel.get("privacy_level", "acknowledge_only"),
                "confirmed":         True,
                "created_at":        now
            }},
            upsert=True
        )
        results["relationships_added"] += 1

    logger.info(f"Admin import complete for {target_username}: {results}")
    return {
        "imported": True,
        "target_username": target_username,
        "results": results,
        "extracted": extracted  # Return full extraction for admin review
    }


# ── Serve PWA ──────────────────────────────────────────────────────────────────
app.mount("/", StaticFiles(directory=os.environ.get("PWA_DIR", "/zoey/pwa"), html=True), name="pwa")
