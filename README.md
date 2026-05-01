# Zoey Graystone — A Full AI Agent and Assistant
# Graystone Solutions: Project Zoey
# 
## Philosophy
Project Zoey Graystone is an exploratory effort to discover the scope and scalabilty of the current private A.I. landscape without the backing of a major congolomorate and teams of developers. Graystone understands that many other project such as this exist our attempt is not to surpase these projects, but merely to understand this endevor and cultivate our own knowledge in the bleeding edge field of agentic AI as we attempt to all reach the singularity together.
## Foundation
Zoey is written in the python language and developed to operate on a static Linux based VPS. Zoey brings her own dependency stack to the host and installs accordingly. A basic Zoey install will operate using an on premise LLM model (Mystrial) and querey more advanced AIs (Anthropic) as needed.

## Evolution
Future plans include several code modules which can be installed for interfacing with various platforms such as social media networks, or smart home systems, for life-managment and assistance platforms.

For more information see: [Project Zoey](https://graystone.solutions/project_zoey)
## Phase 0: Backend Scaffold + PWA Frontend

---

## Stack
| Layer       | Technology                          |
|-------------|-------------------------------------|
| Backend     | Python 3.12, FastAPI, Uvicorn       |
| AI (Standard) | Mistral AI (mistral-small-latest) |
| AI (Advanced) | Anthropic Claude (claude-sonnet)  |
| Database    | MongoDB 7                           |
| DB Admin UI | Mongo Express (port 8081)           |
| Frontend    | Vanilla HTML/CSS/JS PWA             |
| Networking  | ZeroTier (dev), HTTPS (production)  |
| Registry    | GitLab Container Registry           |

---

## First-Time Setup on Local Host Linux Server

### 1. Clone the repo
```bash
git clone https://github.com/GraystoneSolutions/zoeygraystone.git
cd zoeygraystone
```

### 2. Create your .env file
```bash
cp .env.example .env
nano .env
```
Fill in your real API keys. **Never commit .env to git.**

### 3. Run Bootstrap file to start the install to /opt/graystone/zoey
chmod +x zoey_bootstrap.sh
Before running this file, pass the git branch hash as a value.
Example:

./sh zoey_bootstrap.sh master

```
Bootstrap will start the docker build process by the following command:
docker compose up --build -d zoey_docker-compose.yml

```

### 5. Verify everything is running
```bash
docker compose ps
docker compose logs zoeycore --follow
```
---

## Access Points

| Service       | URL                                  |
|---------------|--------------------------------------|
| Zoey Chat PWA | http://10.242.1.1:8000              |
| API Docs      | http://10.242.1.1:8000/docs          |
| API Health    | http://10.242.1.1:8000/health        |
| MongoDB UI    | http://10.242.1.1:8081               |

*(Replace 10.242.1.1 with your dedicated server IP)*

---

## API Endpoints

### POST /chat
Send a message to Zoey.
```json
{
  "message": "Who is Daniel Graystone?",
  "session_id": "optional-session-id",
  "mode": "standard"
}
```
Set `mode` to `"advanced"` to route to Claude instead of Mistral.

### GET /history/{session_id}
Retrieve conversation history for a session.

### DELETE /history/{session_id}
Clear conversation history for a session.

### GET /health
Health check — returns status and version.

---

## Development Workflow

### Watch logs live
```bash
docker compose logs -f
```

### Restart just the backend (after code changes)
```bash
docker compose restart zoeycore
```
*(The volume mount + `--reload` flag means most code changes hot-reload automatically)*

### Stop everything
```bash
docker compose down
```

### Wipe everything including data (careful!)
```bash
docker compose down -v
```

---

## Project Structure
```
zoey/
├── docker-compose.yml          # Full stack definition
├── .env.example                # Copy to .env and fill in secrets
├── .gitignore
├── zoeycore/
│   ├── Dockerfile
│   ├── main.py                 # FastAPI app + AI routing
│   └── requirements.txt
├── pwa/
│   └── index.html              # PWA chat frontend
├── data/
│   └── mongo/                  # MongoDB persistent data (gitignored)
├── logs/                       # App logs (gitignored)
└── backups/                    # Backups (gitignored)
```

---

## Phase Roadmap

| Phase | Goal                                  | Status     |
|-------|---------------------------------------|------------|
| 0     | Backend scaffold + PWA frontend       | ✅ Now     |
| 1     | SwiftUI iOS app                       | Planned    |
| 2     | Memory, personality, long-term context| Planned    |
| 3     | Azure production deployment + AKS     | Planned    |
