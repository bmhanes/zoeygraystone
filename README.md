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
## IN PROGRESS: Phase 3: Personality, Orginization, Persistant Memory
Zoey will get a full personality matrix, backstory, demographics, and her basic modus operandia with a baked in code of ethics and conduct.

Locial flow patterns will be developed for workflow processing and automation.
Memory will be programmed to be persistence per containers or logical flow path. Zoey will be able to recall entire memory chains about whomever she is speaking with, going beyond simple indentification.

Security measures and controls put in place
- Zoey_Developers Group
- Graystone_Staff Group

Rights will begin to form around groups. For example: when Zoey goes live, not every basic user will have the right to turn on Advanced thinking and generate a bill via the Graystone Claude Code API.

Graystone Staff will get access in the future to toolkits not available to the general public. This phase will build the access structure and API backend hooks to handle future toolkits.

API Hooks and Toolkits will be in a future phase.


## COMPLETE Phase 2: Azure AD Hosting and Microsoft Authentication
- Zoey Development environment is live!

Replaced LDAP authentication with Microsoft Azure Active Directory (Entra ID) using OAuth2 / OIDC.

- Users click **Sign in with Microsoft** and are redirected to the Microsoft login page
- Azure AD issues an authorization code that Zoey exchanges for an access token via MSAL
- Microsoft Graph API is queried for user profile and group membership
- Access is restricted to members of the `zoey_users` Azure AD group
- Zoey issues its own signed JWT for subsequent API calls

---
# Zoey Runs in a full Azure Stack. For Self-Hosted Installation Options Please Email:
DevOps At Graystone.Solutions
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


## Phase Roadmap

| Phase | Goal                                        | Status      |
|-------|---------------------------------------------|-------------|
| 0     | Backend scaffold + PWA frontend             | Done        |
| 1     | Local LLM (Mixtral via Ollama)              | Done        |
| 2     | Azure Development + Microsft Authentication | Done        |
| 3     | Personality, Orginization, Persistant Memory| In Progress |
| 4     | Premium Upgrades Token System + API Hooks   | Planned     |
| 5     | Azure Production Deployment with AKS        | Planned     |
| 6     | API Enabled Toolkits + Add-ons for Premium  | Planned     |
| 7     | Swift UI for Apple Ecosystem                | Planned     |
| 8     | UI Migration to Flutter for Cross Platform  | Considering |

