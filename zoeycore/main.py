from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from anthropic import Anthropic
from mistralai import Mistral
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
from datetime import datetime, timezone
from contextlib import asynccontextmanager
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

# ── Lifespan (replaces deprecated @app.on_event) ──────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global conversations, memory
    mongo = connect_mongo()
    db = mongo["zoey"]
    conversations = db["conversations"]
    memory = db["memory"]
    logger.info("Zoey is ready")
    yield
    mongo.close()
    logger.info("Zoey is shutting down")

# ── App Setup ──────────────────────────────────────────────────────────────────
app = FastAPI(title="Zoey AI", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten this in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Clients ────────────────────────────────────────────────────────────────
anthropic_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
mistral_client   = Mistral(api_key=os.environ["MISTRAL_API_KEY"])

# ── Collections (set during lifespan) ─────────────────────────────────────────
conversations = None
memory        = None

# ── Models ────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    mode: str = "standard"   # "standard" = Mistral | "advanced" = Claude

class ChatResponse(BaseModel):
    model_config = {'protected_namespaces': ()}
    reply: str
    engine: str
    session_id: str

# ── System Prompt ──────────────────────────────────────────────────────────────
ZOEY_SYSTEM_PROMPT = """You are Zoey Graystone, an intelligent AI assistant built for 
Graystone Solutions. You are helpful, professional, and security-minded. 
You assist with research, tooling, and general life tasks. 
Be concise but thorough. If you are unsure about something, say so. 
Always prioritize user privacy and data security."""

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "online", "assistant": "Zoey", "version": "0.1.0"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):

    # Load conversation history for this session
    try:
        history = list(conversations.find(
            {"session_id": req.session_id},
            {"_id": 0, "msg_role": 1, "content": 1}
        ).sort("timestamp", 1).limit(20))
    except Exception as e:
        logger.error(f"MongoDB read error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Build message list for the AI
    messages = [{"role": h["msg_role"], "content": h["content"]} for h in history]
    messages.append({"role": "user", "content": req.message})

    # Save user message to MongoDB
    try:
        conversations.insert_one({
            "session_id": req.session_id,
            "msg_role":   "user",
            "content":    req.message,
            "timestamp":  datetime.now(timezone.utc)
        })
    except Exception as e:
        logger.error(f"MongoDB write error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

    # ── Route to correct model ─────────────────────────────────────────────────
    try:
        if req.mode == "advanced":
            # Claude for complex reasoning
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=ZOEY_SYSTEM_PROMPT,
                messages=messages
            )
            reply  = response.content[0].text
            engine = "claude-sonnet"

        else:
            # Mistral for standard responses
            mistral_messages = [{"role": "system", "content": ZOEY_SYSTEM_PROMPT}] + messages
            response = mistral_client.chat.complete(
                model="mistral-small-latest",
                messages=mistral_messages
            )
            reply  = response.choices[0].message.content
            engine = "mistral-small"

    except Exception as e:
        logger.error(f"AI API error: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

    # Save assistant reply to MongoDB
    try:
        conversations.insert_one({
            "session_id": req.session_id,
            "msg_role":   "assistant",
            "content":    reply,
            "engine":     engine,
            "timestamp":  datetime.now(timezone.utc)
        })
    except Exception as e:
        logger.error(f"MongoDB write error saving reply: {e}")

    return ChatResponse(reply=reply, engine=engine, session_id=req.session_id)


@app.get("/history/{session_id}")
def get_history(session_id: str):
    try:
        history = list(conversations.find(
            {"session_id": session_id},
            {"_id": 0}
        ).sort("timestamp", 1))
        return {"session_id": session_id, "messages": history}
    except Exception as e:
        logger.error(f"MongoDB read error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")


@app.delete("/history/{session_id}")
def clear_history(session_id: str):
    try:
        result = conversations.delete_many({"session_id": session_id})
        return {"deleted": result.deleted_count}
    except Exception as e:
        logger.error(f"MongoDB delete error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")


# ── Serve PWA static files ─────────────────────────────────────────────────────
app.mount("/", StaticFiles(directory="/zoey/pwa", html=True), name="pwa")
