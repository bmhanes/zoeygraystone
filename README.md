# Zoey Graystone — AI Agent and Assistant
### Graystone Solutions: Project Zoey

---

## Philosophy

Project Zoey Graystone is an exploratory effort to discover the scope and scalability of the current private AI landscape without the backing of a major conglomerate or teams of developers. Graystone understands that many other projects like this exist — our attempt is not to surpass them, but merely to understand this endeavor and cultivate our own knowledge in the bleeding edge field of agentic AI as we attempt to reach the singularity together.

---

## Foundation

Zoey is written in Python and developed to operate on a cloud-native Azure infrastructure. Zoey brings her own containerized dependency stack via Docker and deploys to Azure Container Apps. A standard Zoey deployment operates using the Mistral API for standard inference and queries Anthropic Claude for advanced reasoning. Authentication is handled via Microsoft Entra ID with full MFA support.

---

## Evolution

Future plans include several code modules for interfacing with various platforms such as social media networks and smart home systems for life management and assistance.

For more information see: [Project Zoey](https://graystone.solutions/project_zoey)

---

## IN PROGRESS: Phase 3 — Personality, Organization, Persistent Memory

Zoey will get a full personality matrix, backstory, demographics, and her basic modus operandi with a baked-in code of ethics and conduct.

Logical flow patterns will be developed for workflow processing and automation.

Memory will be programmed to be persistent per container or logical flow path. Zoey will be able to recall entire memory chains about whomever she is speaking with, going beyond simple identification.

Security measures and controls put in place:
- `Zoey_Developers` Group
- `Graystone_Staff` Group

Rights will begin to form around groups. For example: when Zoey goes live, not every basic user will have the right to enable Advanced mode and generate API costs. Graystone Staff will get access in the future to toolkits not available to the general public. This phase will build the access structure and API backend hooks to handle future toolkits.

API Hooks and Toolkits will be addressed in a future phase.

---

## COMPLETE: Phase 2 — Azure Hosting and Microsoft Authentication

Zoey Development environment is live.

Replaced LDAP authentication with Microsoft Azure Active Directory (Entra ID) using OAuth2 / OIDC.

- Users click **Sign in with Microsoft** and are redirected to the Microsoft login page
- Azure AD issues an authorization code that Zoey exchanges for an access token via MSAL
- Microsoft Graph API is queried for user profile and group membership
- Access is restricted to members of the `zoey_users` Azure AD group
- Zoey issues its own signed JWT for subsequent API calls

---

# Zoey Runs on a Full Azure Stack. For Self-Hosted Installation Options Please Email:
**DevOps at Graystone.Solutions**

---

## Current Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| AI (Standard) | Mistral API (mistral-small-latest) |
| AI (Advanced) | Anthropic Claude Sonnet |
| AI (On-Premise Option) | Mixtral 8x7b via Ollama |
| Authentication | Microsoft Entra ID — OAuth2 / OIDC + MFA |
| Session Management | JWT (HS256, 8hr expiry) |
| Database | Azure Cosmos DB for MongoDB (DocumentDB) |
| Container Registry | Azure Container Registry (ACR) |
| Hosting | Azure Container Apps |
| Secrets | Azure Key Vault |
| Frontend | Vanilla HTML/CSS/JS PWA |
| DNS | GoDaddy |
| SSL | Wildcard Certificate |
| Source Control | GitHub |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/auth/login` | Redirects browser to Microsoft login |
| `GET` | `/auth/callback` | Receives auth code, issues Zoey JWT |
| `GET` | `/auth/logout` | Redirects to Microsoft logout |
| `POST` | `/chat` | Send a message (Bearer token required) |
| `GET` | `/history` | Retrieve conversation history |
| `DELETE` | `/history` | Clear conversation history |
| `POST` | `/memory` | Save a fact to Zoey's memory |
| `GET` | `/health` | Health check |

Set `mode` to `"advanced"` in `/chat` to route to Claude instead of Mistral.

---

## Project Structure

```
zoey/
├── zoey_docker-compose.yml     # On-premise stack definition
├── zoeybootstrap.sh            # On-premise deployment bootstrap
├── .env.example                # Copy to .env and fill in secrets
├── .gitignore
├── Dockerfile                  # Root Dockerfile for Azure builds
├── Ubuntu24NetworkHotfixes/    # On-premise network fix scripts
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

## Phase Roadmap

| Phase | Goal | Status |
|---|---|---|
| 0 | Backend scaffold + PWA frontend | ✅ Complete |
| 1 | Local LLM (Mixtral via Ollama) | ✅ Complete |
| 2 | Azure deployment + Microsoft Authentication | ✅ Complete |
| 3 | Personality, Organization, Persistent Memory | 🔄 In Progress |
| 4 | Premium upgrades, token system + API hooks | Planned |
| 5 | Azure production deployment with AKS | Planned |
| 6 | API-enabled toolkits + add-ons for premium | Planned |
| 7 | SwiftUI for Apple ecosystem | Planned |
| 8 | UI migration to Flutter for cross-platform | Considering |

---

## About

**Graystone Solutions** — Advanced IT & AI Security Consulting
[graystone.solutions](https://graystone.solutions)
