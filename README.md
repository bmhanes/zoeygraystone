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

## CURRENT ### 
## Phase 1: Local LLM and LDAP
Moved from Mistral API calls to local Mistral ollama with pull of LLM mixtral:8x7b
Added support for LDAP Authentication to a local DC when testing in a local network

## Phase 0: Backend Scaffold + PWA Frontend
## Stack
| Layer       | Technology                          |
|-------------|-------------------------------------|
| Backend     | Python 3.12, FastAPI, Uvicorn       |
| AI (Standard) | Mistral AI (mistral-small-latest) |
| AI (Advanced) | Anthropic Claude (claude-sonnet)  |
| Database    | MongoDB 7 (4.4 if lacking AVS)      |
| DB Admin UI | Mongo Express (port 8081)           |
| Frontend    | Vanilla HTML/CSS/JS PWA             |
| Networking  | ZeroTier (dev), HTTPS (production)  |
| Registry    | Github Registry                     |

---

## First-Time Setup on Local Host Linux Server

### 1. Clone the repo
```bash
git clone https://github.com/GraystoneSolutions/zoeygraystone.git
cd zoeygraystone
```
### 2. Run Bootstrap file to start the install to /opt/graystone/zoey
chmod +x zoey_bootstrap.sh
Before running this file, pass the git branch hash as a value.
Example:

./sh zoey_bootstrap.sh master

### 3. Create your .env file
```bash
cp .env.example .env
nano .env
```
Fill in your real API keys. **Never commit .env to git.**

```
### 4. Create your .env file
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
---
Emergency Maintenance Controls
# CAUTION: Know what you are doing! This will nuke all containers and roll a clean Zoey!
# Show all running Docker Containers
docker ps -a

Build Docker Containers Up:
docker compose -f /home/graystone/zoey/zoey_docker-compose.yml up

Tear Dockers Containers Down:
docker compose -f /home/graystone/zoey/zoey_docker-compose.yml down

Fix Corrupted Containers
sudo kill -9 $(docker inspect zoeycore --format='{{.State.Pid}}')
sudo kill -9 $(docker inspect zoeydb-ui --format='{{.State.Pid}}')
sudo kill -9 $(docker inspect zoeydb --format='{{.State.Pid}}')

# Force Remove all Containers
docker rm -f $(docker ps -aq)

# Clean up and restart docker
docker network prune -f
sudo systemctl restart docker
docker ps -a

# Reinstall all containers
docker compose -f /home/graystone/zoey/zoey_docker-compose.yml up -d


## Phase 1: Project Structure
```
zoey/
├── docker-compose.yml          # Full stack definition
├── .env.example                # Copy to .env and fill in secrets
├── .gitignore
├── zoeycore/
│   ├── Dockerfile
│   ├── main.py                 # FastAPI app + AI routing
│   └── auth.py                 # Authenticate to LDAP Server
│   └── requirements.txt|   
├── pwa/
│   └── index.html              # PWA chat frontend
├── data/
│   └── mongo/                  # MongoDB persistent data (gitignored)
├── logs/                       # App logs (gitignored)
└── backups/                    # Backups (gitignored)
```

---

## Zoey Phase Roadmap

| Phase | Goal                                  | Status     |
|-------|---------------------------------------|------------|
| 0     | Backend scaffold + PWA frontend       | ✅ Done    |
| 1     | Authentication, Memory, Persistence   | In Test    |           
| 2     | Memory, personality, long-term context| Planned    |
| 3     | Azure production deployment + AKS     | Planned    |
| 4     | Swift UI for Apple Ecosystem          | Planned    |
