# Zoey Graystone — AI Agent and Assistant
# Graystone Solutions: Project Zoey

## Philosophy

Project Zoey Graystone is an exploratory effort to discover the scope and scalability of the current private AI landscape without the backing of a major conglomerate or teams of developers. Graystone understands that many other projects like this exist — our attempt is not to surpass them, but merely to understand this endeavor and cultivate our own knowledge in the bleeding edge field of agentic AI as we attempt to reach the singularity together.

## Foundation

Zoey is written in Python and developed to operate on a Linux-based VPS. Zoey brings her own dependency stack to the host and installs accordingly. A basic Zoey install operates using an on-premise LLM model (Mixtral via Ollama) and queries more advanced AI (Anthropic Claude) as needed.

## Evolution

Future plans include several code modules for interfacing with various platforms such as social media networks and smart home systems for life-management and assistance.

For more information see: [Project Zoey](https://graystone.solutions/project_zoey)

---

## CURRENT — Phase 2: Azure AD Authentication

Replaced LDAP authentication with Microsoft Azure Active Directory (Entra ID) using OAuth2 / OIDC.

- Users click **Sign in with Microsoft** and are redirected to the Microsoft login page
- Azure AD issues an authorization code that Zoey exchanges for an access token via MSAL
- Microsoft Graph API is queried for user profile and group membership
- Access is restricted to members of the `zoey_users` Azure AD group
- Zoey issues its own signed JWT for subsequent API calls

## Phase 1: Local LLM

Moved from Mistral API calls to a locally hosted Mixtral model via Ollama (`mixtral:8x7b`).

## Phase 0: Backend Scaffold + PWA Frontend

---

## Stack

| Layer          | Technology                              |
|----------------|-----------------------------------------|
| Backend        | Python 3.12, FastAPI, Uvicorn           |
| AI (Standard)  | Mixtral 8x7b (Ollama, on-premise)       |
| AI (Advanced)  | Anthropic Claude (claude-sonnet)        |
| Auth           | Azure Active Directory (MSAL / OIDC)    |
| Database       | MongoDB 8                               |
| DB Admin UI    | Mongo Express (port 8081)               |
| Frontend       | Vanilla HTML/CSS/JS PWA                 |
| Networking     | ZeroTier (dev), HTTPS (production)      |
| Registry       | GitHub Container Registry               |

---

## First-Time Setup

### 1. Clone the repo

```bash
git clone https://github.com/GraystoneSolutions/zoeygraystone.git
cd zoeygraystone
```

### 2. Run the bootstrap script

```bash
chmod +x zoeybootstrap.sh
./zoeybootstrap.sh master
```

The bootstrap installs Zoey to `/opt/graystone/zoey` and triggers the Docker build.

### 3. Create your `.env` file

```bash
cp .env.example .env
nano .env
```

Fill in all required values. **Never commit `.env` to git.**

```env
# Anthropic
ANTHROPIC_API_KEY=

# Azure AD (required for login)
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
AZURE_TENANT_ID=
AZURE_REDIRECT_URI=https://<your-domain>/auth/callback

# Zoey Auth
ZOEY_AD_GROUP=zoey_users
JWT_SECRET=
JWT_EXPIRY_HOURS=8

# MongoDB
MONGO_URI=mongodb://zoeydb:27017/zoey

# Ollama
OLLAMA_URL=http://ollama:11434
OLLAMA_MODEL=mixtral:8x7b
```

### 4. Start the stack

```bash
docker compose -f zoey_docker-compose.yml up --build -d
```

### 5. Verify everything is running

```bash
docker compose ps
docker compose logs zoeycore --follow
```

---

## Azure AD App Registration

Before users can log in you must register Zoey in your Azure tenant:

1. **Azure Portal → App registrations → New registration**
2. Set the redirect URI to `https://<your-domain>/auth/callback`
3. Under **API permissions**, add `User.Read` (Microsoft Graph, delegated)
4. Create a **Client secret** and copy it to `AZURE_CLIENT_SECRET`
5. Ensure the `zoey_users` group exists in your tenant and users are members of it

---

## Access Points

| Service       | URL                              |
|---------------|----------------------------------|
| Zoey Chat PWA | http://10.242.1.1:8000           |
| API Docs      | http://10.242.1.1:8000/docs      |
| API Health    | http://10.242.1.1:8000/health    |
| MongoDB UI    | http://10.242.1.1:8081           |

*(Replace `10.242.1.1` with your server IP)*

---

## API Endpoints

| Method   | Path             | Description                                   |
|----------|------------------|-----------------------------------------------|
| `GET`    | `/auth/login`    | Redirects browser to Microsoft login          |
| `GET`    | `/auth/callback` | Receives auth code, issues Zoey JWT           |
| `POST`   | `/chat`          | Send a message (Bearer token required)        |
| `GET`    | `/history`       | Retrieve conversation history                 |
| `DELETE` | `/history`       | Clear conversation history                    |
| `POST`   | `/memory`        | Save a fact to Zoey's memory                  |
| `GET`    | `/health`        | Health check                                  |

Set `mode` to `"advanced"` in `/chat` to route to Claude instead of Mixtral.

---

## Project Structure

```
zoey/
├── zoey_docker-compose.yml     # Full stack definition
├── .env.example                # Copy to .env and fill in secrets
├── .gitignore
├── zoeycore/
│   ├── Dockerfile
│   ├── main.py                 # FastAPI app + AI routing
│   ├── auth.py                 # Azure AD OIDC authentication
│   └── requirements.txt
├── pwa/
│   └── index.html              # PWA chat frontend
├── data/
│   └── mongo/                  # MongoDB persistent data (gitignored)
├── logs/                       # App logs (gitignored)
└── backups/                    # Backups (gitignored)
```

---

## Emergency Maintenance

```bash
# Show running containers
docker ps -a

# Start stack
docker compose -f /opt/graystone/zoey/zoey_docker-compose.yml up -d

# Stop stack
docker compose -f /opt/graystone/zoey/zoey_docker-compose.yml down

# Force remove all containers
docker rm -f $(docker ps -aq)

# Clean up networks and restart Docker
docker network prune -f
sudo systemctl restart docker

# Kill a specific stuck container
sudo kill -9 $(docker inspect zoeycore --format='{{.State.Pid}}')
sudo kill -9 $(docker inspect zoeydb-ui --format='{{.State.Pid}}')
sudo kill -9 $(docker inspect zoeydb --format='{{.State.Pid}}')
```

---

## Phase Roadmap

| Phase | Goal                                        | Status      |
|-------|---------------------------------------------|-------------|
| 0     | Backend scaffold + PWA frontend             | Done        |
| 1     | Local LLM (Mixtral via Ollama)              | Done        |
| 2     | Azure AD authentication + persistent memory | In Progress |
| 3     | Azure production deployment + AKS           | Planned     |
| 4     | Swift UI for Apple Ecosystem                | Planned     |
