#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Zoey Bootstrap Script — Graystone Solutions
#  Pull the latest build commit and sets up /opt/graystone/zoey
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ── Config ──────────────────────────────────────────────────────
GITHUB_REPO="https://github.com/GraystoneSolutions/zoeygraystone.git"   # ← update if needed
INSTALL_DIR="/opt/graystone/zoey"
COMMIT="${1:-}"   # Pass commit hash as first argument

# ── Colors ──────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Banner ──────────────────────────────────────────────────────
echo -e "${BOLD}"
echo "  ╔═══════════════════════════════════════╗"
echo "  ║   ZOEY — Graystone Solutions          ║"
echo "  ║   Bootstrap Installer                 ║"
echo "  ╚═══════════════════════════════════════╝"
echo -e "${NC}"

# ── Require root ────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && die "Run this script as root: sudo $0 <commit-hash>"

# ── Require commit hash ──────────────────────────────────────────
if [[ -z "$COMMIT" ]]; then
  die "Usage: sudo $0 <commit-hash>\n       Example: sudo $0 a3f9c21"
fi

info "Target commit : ${BOLD}${COMMIT}${NC}"
info "Install path  : ${BOLD}${INSTALL_DIR}${NC}"
echo ""

# ── Check dependencies ───────────────────────────────────────────
for cmd in git docker; do
  command -v "$cmd" &>/dev/null || die "'$cmd' is not installed. Please install it first."
done
success "Dependencies found (git, docker)"

# ── Create /opt/graystone if needed ──────────────────────────────
if [[ ! -d /opt/graystone ]]; then
  info "Creating /opt/graystone..."
  mkdir -p /opt/graystone
  success "Created /opt/graystone"
fi

# ── Handle existing install ───────────────────────────────────────
if [[ -d "$INSTALL_DIR" ]]; then
  warn "Directory ${INSTALL_DIR} already exists."
  read -rp "  Remove and reinstall? [y/N]: " confirm
  [[ "${confirm,,}" == "y" ]] || die "Aborted by user."
  rm -rf "$INSTALL_DIR"
  success "Removed existing installation"
fi

# ── Clone repo ────────────────────────────────────────────────────
info "Cloning repository..."
git clone "$GITHUB_REPO" "$INSTALL_DIR" 2>&1 | sed 's/^/  /'
success "Repository cloned"

# ── Checkout specific commit ──────────────────────────────────────
info "Checking out commit ${COMMIT}..."
cd "$INSTALL_DIR"
git checkout "$COMMIT" 2>&1 | sed 's/^/  /'
success "Checked out commit ${COMMIT}"

# ── Verify required files exist ───────────────────────────────────
info "Verifying required files..."
REQUIRED_FILES=(
  "zoey_docker-compose.yml"
  "zoeycore/Dockerfile"
  "zoeycore/main.py"
  "zoeycore/requirements.txt"
  "pwa/index.html"
)

MISSING=0
for f in "${REQUIRED_FILES[@]}"; do
  if [[ -f "$INSTALL_DIR/$f" ]]; then
    echo -e "  ${GREEN}✓${NC} $f"
  else
    echo -e "  ${RED}✗${NC} $f  ← MISSING"
    MISSING=$((MISSING + 1))
  fi
done

[[ $MISSING -gt 0 ]] && die "$MISSING required file(s) missing from this commit. Check your repo."
success "All required files present"

# ── Create runtime directories ────────────────────────────────────
info "Creating runtime directories..."
chmod 755 /opt/graystone
mkdir -p \
  "$INSTALL_DIR/data/mongo" \
  "$INSTALL_DIR/logs" \
  "$INSTALL_DIR/backups"
success "Runtime directories created"

# ── Set up .env if missing ────────────────────────────────────────
if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  if [[ -f "$INSTALL_DIR/.env.example" ]]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo ""
    warn "┌─────────────────────────────────────────────────────┐"
    warn "│  ACTION REQUIRED — API Keys Not Configured          │"
    warn "│                                                     │"
    warn "│  .env has been created from .env.example            │"
    warn "│  You MUST add your API keys before continuing.      │"
    warn "│                                                     │"
    warn "│  Required keys:                                     │"
    warn "│    ANTHROPIC_API_KEY                                │"
    warn "│    MISTRAL_API_KEY                                  │"
    warn "│    MONGO_EXPRESS_PASSWORD                           │"
    warn "└─────────────────────────────────────────────────────┘"
    echo ""
    read -rp "  Open .env in nano now to configure your API keys? [Y/n]: " open_confirm
    if [[ "${open_confirm,,}" != "n" ]]; then
      nano "$INSTALL_DIR/.env"
    fi
    echo ""
    # Verify the user actually edited the file — check for placeholder values
    if grep -qE "your_.*_here|changeme" "$INSTALL_DIR/.env"; then
      warn "Placeholder values detected in .env — your API keys may not be set."
      read -rp "  Continue anyway? [y/N]: " force_confirm
      [[ "${force_confirm,,}" == "y" ]] || die "Halted. Edit ${INSTALL_DIR}/.env and re-run the script."
    fi
    success ".env configured"
  else
    die "No .env.example found in ${INSTALL_DIR}. Cannot continue without a template to configure."
  fi
else
  success ".env already exists — skipping"
fi
# ── Permissions ───────────────────────────────────────────────────
chown -R root:docker "$INSTALL_DIR" 2>/dev/null || true
chmod -R 750 "$INSTALL_DIR"
chmod 600 "$INSTALL_DIR/.env" 2>/dev/null || true
chmod 044 "$INSTALL_DIR/.env.example" 2>/dev/null || true
success "Permissions set"

# ── Docker Build Phase ───────────────────────────────────────────────────
info "Building Docker images..."
docker compose -f "$INSTALL_DIR/zoey_docker-compose.yml" build
success "Docker images built"

# ── Summary ───────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${BOLD}  Zoey Install Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}Install path:${NC}  ${INSTALL_DIR}"
echo -e "  ${BOLD}Commit:${NC}        ${COMMIT}"
echo ""
echo -e "  ${BOLD}Next steps:${NC}"
echo -e "  ${CYAN}1.${NC}  Watch the logs:      ${BOLD}docker compose logs -f${NC}"
#echo -e "  ${CYAN}2.${NC}  Install Additional Services:      ${BOLD}docker compose logs -f${NC}"
echo ""
