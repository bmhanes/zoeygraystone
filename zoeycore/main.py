from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from anthropic import Anthropic
from mistralai import Mistral
from pymongo import MongoClient
from datetime import datetime, timezone
import os

# ── App Setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title="Zoey AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten this in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Clients ────────────────────────────────────────────────────────────────
anthropic_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
mistral_client   = Mistral(api_key=os.environ["MISTRAL_API_KEY"])

# ── MongoDB ────────────────────────────────────────────────────────────────────
mongo = MongoClient(os.environ.get("MONGO_URI", "mongodb://zoeydb:27017/zoey"))
db    = mongo["zoey"]
conversations = db["conversations"]
memory        = db["memory"]

# ── Models ─────────────────────────────────────────────────────────────────────
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
Always prioritize user privacy and data security. """

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "online", "assistant": "Zoey", "version": "0.1.0"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # Load conversation history for this session
    history = list(conversations.find(
        {"session_id": req.session_id},
        {"_id": 0, "role": 0, "session_id": 0, "timestamp": 0}
    ).sort("timestamp", 1).limit(20))

    # Build message list for the AI
    messages = [{"role": h["msg_role"], "content": h["content"]} for h in history]
    messages.append({"role": "user", "content": req.message})

    # Save user message to MongoDB
    conversations.insert_one({
        "session_id": req.session_id,
        "msg_role":   "user",
        "content":    req.message,
        "timestamp":  datetime.now(timezone.utc)
    })

    # ── Route to correct model ─────────────────────────────────────────────────
    if req.mode == "advanced":
        # Claude for complex reasoning
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=ZOEY_SYSTEM_PROMPT,
            messages=messages
        )
        reply      = response.content[0].text
        engine     = "claude-sonnet"

    else:
        # Mistral for standard responses
        mistral_messages = [{"role": "system", "content": ZOEY_SYSTEM_PROMPT}] + messages
        response = mistral_client.chat.complete(
            model="mistral-small-latest",
            messages=mistral_messages
        )
        reply      = response.choices[0].message.content
        engine     = "mistral-small"

    # Save assistant reply to MongoDB
    conversations.insert_one({
        "session_id": req.session_id,
        "msg_role":   "assistant",
        "content":    reply,
        "engine":     engine,
        "timestamp":  datetime.now(timezone.utc)
    })

    return ChatResponse(reply=reply, engine=engine, session_id=req.session_id)


@app.get("/history/{session_id}")
def get_history(session_id: str):
    history = list(conversations.find(
        {"session_id": session_id},
        {"_id": 0}
    ).sort("timestamp", 1))
    return {"session_id": session_id, "messages": history}


@app.delete("/history/{session_id}")
def clear_history(session_id: str):
    result = conversations.delete_many({"session_id": session_id})
    return {"deleted": result.deleted_count}


# ── Serve PWA static files ─────────────────────────────────────────────────────
app.mount("/", StaticFiles(directory="/zoey/pwa", html=True), name="pwa")
