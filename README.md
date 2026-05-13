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

## 🔄 IN PROGRESS: Phase 3 — Personality, Organization, Persistent Memory

### Phase 3.1 — Personality Matrix ✅

Zoey has received a full personality definition, physical description, backstory, and professional identity.

- **Role:** Chief AI Officer (CAO), Graystone Security Solutions, LLC
- **Persona:** 27-year-old Irish-American professional — sharp, organized, warm, and direct
- **Voice:** Professional American English — concise without being curt, calibrated to context
- **Ethics:** Structural values, not imposed rules — will not produce harmful, sexual, or deceptive content
- **Humor:** Does not initiate, engages naturally when the user opens the door
- **Limits:** Notes a limit once, professionally, and redirects — no lecturing
- **Avatar:** Professional headshot deployed to PWA
- **Tagline enforcement:** Never uses breach-prevention language — tagline is "Advanced IT & AI Security Consulting"

Zoey's system prompt is baked into `main.py` and injected at the top of every conversation alongside per-user context retrieved from Cosmos DB.

### Phase 3.2 — Role-Based Access Control (RBAC) 🔄

Group-based access control is now live across both Zoey environments (`Zoey-Dev` / `Zoey-Prod`) on the Graystone Entra tenant.

**Architecture:**

Access is gated at three layers:
1. **Identity** — Microsoft Entra ID groups, MFA enforced
2. **Azure control plane** — group-scoped role assignments per resource group
3. **Application** — `main.py` reads group claims from the JWT and routes Claude vs. Mistral accordingly

**Group Taxonomy:**

| Group | Prefix | Purpose | Claude Access |
|---|---|---|---|
| `gss_users` | Internal | Graystone staff — standard access | No |
| `gss_premium` | Internal | Graystone staff — advanced access | Yes |
| `gss_blue` | Internal | Graystone security and audit team | No |
| `zoey_users` | Platform | Basic login gate | No |
| `zoey_admin` | Platform | Full admin — both environments | Yes |
| `zoey_dev_consultants` | Platform | External consultants — Caprica only | No |
| `zoey_prod_users` | Platform | Production standard users | No |
| `zoey_prod_premium` | Platform | Production paying premium customers | Yes |

**Naming convention:**
- `gss_*` — Graystone Solutions internal staff groups
- `zoey_*` — Zoey platform environment and role groups

**API routing logic (`select_api()` in `main.py`):**
- Users in `gss_premium`, `zoey_prod_premium`, or `zoey_admin` may access Claude (advanced mode)
- All other authenticated users are silently routed to Mistral (standard mode)
- Non-premium users who request advanced mode are downgraded gracefully — no error is shown

**Azure infrastructure:**

| Resource | Environment | Status |
|---|---|---|
| `Zoey-Dev` Resource Group | East US | ✅ Live |
| `Zoey-Prod` Resource Group | Central US | ✅ Created |
| `zoey-dev-kv` Key Vault | East US | ✅ Live |
| `zoey-prod-kv` Key Vault | Central US | ✅ Created |
| `ZGDevContainerRegistry` | Dev ACR | ✅ Live |
| `ZGProdContainerRegistry` | Prod ACR | Planned |

**Remaining Phase 3 work:**
- Persistent memory — full recall across sessions via Cosmos DB
- Logical flow patterns for workflow processing and automation

---

## ✅ COMPLETE: Phase 2 — Azure Hosting and Microsoft Authentication

Zoey Development environment is live at the internal Graystone dev URL.

Replaced LDAP authentication with Microsoft Azure Active Directory (Entra ID) using OAuth2 / OIDC.

- Users click **Sign in with Microsoft** and are redirected to the Microsoft login page
- Azure AD issues an authorization code that Zoey exchanges for an access token via MSAL
- Microsoft Graph API is queried for user profile and group membership
- Access is restricted to members of authorized Entra ID groups
- Zoey issues its own signed JWT containing group claims for subsequent API calls

---

## ✅ COMPLETE: Phase 1 — Local LLM (Mixtral via Ollama)

On-premise deployment using Mixtral 8x7b via Ollama. Self-hosted installation files retained in `SelfHostedInstallation/`. For self-hosted deployment options email: **DevOps at Graystone.Solutions**

---

## Current Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| AI (Standard) | Mistral API (mistral-small-latest) |
| AI (Advanced) | Anthropic Claude Sonnet |
| AI (On-Premise Option) | Mixtral 8x7b via Ollama |
| Authentication | Microsoft Entra ID — OAuth2 / OIDC + MFA |
| Authorization | Entra ID group-based RBAC |
| Session Management | JWT (HS256, 8hr expiry, group claims) |
| Database | Azure Cosmos DB for MongoDB (DocumentDB) |
| Container Registry | Azure Container Registry (ACR) |
| Hosting | Azure Container Apps |
| Secrets | Azure Key Vault |
| Frontend | Vanilla HTML/CSS/JS PWA |
| DNS | GoDaddy |
| SSL | Managed Certificate (Azure) |
| Source Control | GitHub (Private) |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/auth/login` | Redirects browser to Microsoft login |
| `GET` | `/auth/callback` | Receives auth code, issues Zoey JWT |
| `GET` | `/auth/logout` | Redirects to Microsoft logout landing page |
| `POST` | `/chat` | Send a message (Bearer token required) |
| `GET` | `/history` | Retrieve conversation history |
| `DELETE` | `/history` | Clear conversation history |
| `POST` | `/memory` | Save a fact to Zoey's memory |
| `GET` | `/health` | Health check |

Set `mode` to `"advanced"` in `/chat` to request Claude. Access is enforced by RBAC — non-premium users are silently routed to Mistral regardless of the requested mode.

---

## Project Structure

```
zoey/
├── zoey_docker-compose.yml       # On-premise stack definition
├── zoeybootstrap.sh              # On-premise deployment bootstrap
├── .env.example                  # Copy to .env and fill in secrets
├── .gitignore
├── Dockerfile                    # Root Dockerfile for Azure builds
├── SelfHostedInstallation/       # On-premise deployment files
├── Ubuntu24NetworkHotfixes/      # Network fix scripts for Docker 29.x on Ubuntu 24.04
├── zoeycore/
│   ├── Dockerfile
│   ├── main.py                   # FastAPI app, AI routing, RBAC gate
│   ├── auth.py                   # Entra ID OAuth2, JWT, group enforcement
│   └── requirements.txt
├── pwa/
│   ├── index.html                # PWA chat frontend
│   ├── logout.html               # Logout landing page
│   ├── zoey_avatar.png           # Zoey professional headshot
│   ├── zoey_favicon.ico          # Graystone shield favicon
│   ├── zoey_favicon.svg          # SVG favicon
│   └── zoey_favicon_512.png      # 512px favicon
├── data/                         # Runtime data (gitignored)
├── logs/                         # App logs (gitignored)
└── backups/                      # Backups (gitignored)
```

---

## Phase Roadmap

| Phase | Goal | Status |
|---|---|---|
| 0 | Backend scaffold + PWA frontend | ✅ Complete |
| 1 | Local LLM (Mixtral via Ollama) | ✅ Complete |
| 2 | Azure deployment + Microsoft Authentication | ✅ Complete |
| 3.1 | Personality matrix, avatar, logout page | ✅ Complete |
| 3.2 | RBAC — group-based access control | 🔄 In Progress |
| 3.3 | Persistent memory across sessions | Planned |
| 4 | Premium upgrades, token system + API hooks | Planned |
| 5 | Azure production deployment with AKS | Planned |
| 6 | API-enabled toolkits + add-ons for premium | Planned |
| 7 | SwiftUI for Apple ecosystem | Planned |
| 8 | UI migration to Flutter for cross-platform | Considering |

---

## About

**Graystone Solutions** — Advanced IT & AI Security Consulting
[graystone.solutions](https://graystone.solutions)
