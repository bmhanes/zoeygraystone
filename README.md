# Zoey Graystone — AI Agent & Assistant
### Graystone Solutions | Project Zoey

---

## Philosophy

Project Zoey Graystone is an exploratory effort to discover the scope and scalability of the current private AI landscape without the backing of a major conglomerate and teams of developers. Graystone understands that many other projects such as this exist — our attempt is not to surpass these projects, but merely to understand this endeavor and cultivate our own knowledge in the bleeding edge field of agentic AI as we attempt to reach the singularity together.

---

## Foundation

Zoey is written in Python and developed to operate on a cloud-native infrastructure hosted on Microsoft Azure. Zoey brings her own containerized dependency stack via Docker and deploys to Azure Container Apps. A standard Zoey deployment operates using the Mistral API for standard inference and queries Anthropic Claude for advanced reasoning. Authentication is handled via Microsoft Entra ID (Azure Active Directory) with full MFA support.

---

## Current Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| AI (Standard) | Mistral API (mistral-small-latest) |
| AI (Advanced) | Anthropic Claude Sonnet |
| AI (On-Premise Option) | Mixtral 8x7b via Ollama (local inference) |
| Authentication | Microsoft Entra ID — OAuth2 Authorization Code Flow + MFA |
| Session Management | JWT (HS256, 8hr expiry) |
| Database | Azure Cosmos DB for MongoDB (DocumentDB) |
| Frontend | Vanilla HTML/CSS/JS PWA |
| Container Registry | Azure Container Registry (ACR) |
| Hosting | Azure Container Apps (ACA) |
| DNS | GoDaddy → zoey.graystone.solutions |
| SSL | Wildcard *.graystone.solutions |
| Registry | GitHub |

---

## Phase 3 — Azure Cloud Migration

Phase 3 migrated Zoey from on-premise infrastructure to a fully cloud-native Azure deployment. Key changes:

**Authentication** — LDAP against Windows Active Directory replaced with Microsoft Entra ID OAuth2 Authorization Code Flow. Users authenticate via the Microsoft login page with full MFA support. Group membership (`zoey_users` security group in Entra ID) is enforced via the Microsoft Graph API before a JWT is issued. No credentials are handled by Zoey directly.

**Database** — Self-hosted MongoDB replaced with Azure Cosmos DB for MongoDB (DocumentDB). Full MongoDB API compatibility with zero code changes to `pymongo`. Free tier provides 32GB storage at no cost during development.

**Inference** — Local Ollama/Mixtral replaced with Mistral API for standard mode. Ollama remains supported as an optional on-premise inference backend via `OLLAMA_URL` environment variable. Claude handles advanced reasoning in both deployment modes.

**Infrastructure** — ZeroTier dev network replaced with Azure Container Apps. Docker Compose replaced with ACR image builds and ACA deployments. Container Apps provides built-in HTTPS, custom domain support, and scales to zero when idle.

**User Onboarding** — To grant a user access to Zoey:
1. Create their account in Microsoft Entra ID (or sync from on-premise AD)
2. Add them to the `zoey_users` security group
3. User signs in at `zoey.graystone.solutions` with their Microsoft account

No code changes needed per user — Entra ID is the single source of truth.

---

## First-Time Setup

### 1. Configure `.env`

```bash
cp .env.example .env
nano .env
```

Fill in all required values. **Never commit `.env` to git.**

### 2. Run locally for development

```bash
cd zoeycore
source ../.venv/bin/activate
export $(grep -v '^#' ../.env | xargs -d '\n')
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Verify

```bash
curl http://localhost:8000/health
```

Open `http://localhost:8000` and sign in with your Microsoft account.

---

## Access Points

| Environment | URL |
|---|---|
| Production | https://zoey.graystone.solutions |
| Local Dev | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| API Health | http://localhost:8000/health |
| Azure Portal | https://portal.azure.com |
| Cosmos DB | Azure Portal → Cosmos DB → Data Explorer |

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/auth/login` | None | Redirect to Microsoft login page |
| GET | `/auth/callback` | None | OAuth2 callback — issues Zoey JWT |
| GET | `/auth/logout` | None | Redirect to Microsoft logout |
| GET | `/health` | None | Health check |
| POST | `/chat` | JWT | Send message to Zoey |
| GET | `/history` | JWT | Retrieve conversation history |
| DELETE | `/history` | JWT | Clear conversation history |
| POST | `/memory` | JWT | Save a fact to Zoey's memory |

Set `mode` to `"advanced"` in the chat request to route to Claude instead of Mistral.

---

## Authentication Flow

```
User opens Zoey PWA
→ Clicks "Sign in with Microsoft"
→ Redirected to Microsoft login page
→ User enters credentials + MFA
→ Microsoft redirects back to /auth/callback with auth code
→ Zoey exchanges code for Graph API token
→ Zoey validates zoey_users group membership
→ Zoey issues signed JWT
→ Chat session begins
```

---

## Project Structure

```
zoey/
├── zoey_docker-compose.yml     # On-premise stack definition
├── .env.example                # Copy to .env and fill in secrets
├── .gitignore
├── zoeybootstrap.sh            # On-premise deployment bootstrap
├── Ubuntu24NetworkHotfixes/
│   ├── zoey_network_fix.sh     # nftables fix for Docker 29.x
│   └── zoey-netfix.service     # systemd unit for network fix
├── zoeycore/
│   ├── Dockerfile
│   ├── main.py                 # FastAPI app + AI routing
│   ├── auth.py                 # Entra ID OAuth2 + JWT
│   └── requirements.txt
├── pwa/
│   └── index.html              # PWA chat frontend
├── data/                       # Runtime data (gitignored)
├── logs/                       # App logs (gitignored)
└── backups/                    # Backups (gitignored)
```

---

## Azure Resources

| Resource | Name | Purpose |
|---|---|---|
| Entra ID App | Zoey | OAuth2 authentication |
| Cosmos DB | zbdevcosmodocumentdb | Per-user conversation and memory storage |
| Container Registry | ZGDevContainerRegistry | Docker image storage |
| Container Apps | zoey | Production hosting |
| Resource Group | Zoey-Dev | All dev resources |

---

## Phase Roadmap

| Phase | Goal | Status |
|---|---|---|
| 0 | Backend scaffold + PWA frontend | ✅ Complete |
| 1 | LDAP auth, local Mixtral, per-user MongoDB | ✅ Complete |
| 2 | Long-term memory, personality, context persistence | 🔄 In Progress |
| 3 | Azure cloud migration — Entra ID, Cosmos DB, Container Apps | ✅ Complete |
| 4 | Personalized containers & plugin framework | Planned |
| Later | SwiftUI for Apple ecosystem | Planned |

---

## About

**Graystone Solutions** — Advanced IT & AI Security Consulting  
[graystone.solutions](https://graystone.solutions)
