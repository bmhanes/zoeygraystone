!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Zoey Bootstrap Script — Graystone Solutions
#  Pull the latest build commit and sets up /home/graystone/zoey
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ── Config ──────────────────────────────────────────────────────
GITHUB_REPO="https://github.com/GraystoneSolutions/zoeygraystone.git"   # ← update if needed
INSTALL_DIR="/home/graystone/zoey"
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

# ── Create /home/graystone if needed ──────────────────────────────
if [[ ! -d /home/graystone ]]; then
  info "Creating /home/graystone..."
  mkdir -p /home/graystone
  success "Created /home/graystone"
# ── Create Zoey User ───────────────────────────────────────────
sudo useradd --system --no-create-home --shell /usr/sbin/nologin zoey
sudo mkdir -p /home/graystone/zoey
sudo chown -R zoey:zoey /home/graystone
sudo chmod 750 /home/graystone/zoey
sudo usermod -aG docker zoey

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
chmod 755 /home/graystone
mkdir -p \
  "$INSTALL_DIR/data/mongo" \
  "$INSTALL_DIR/logs" \
  "$INSTALL_DIR/backups"
success "Runtime directories created"

# ── Assign ownership to service user ─────────────────────────────
info "Setting ownership to service user"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"
chmod 750 "$INSTALL_DIR"
chmod 755 \
  "$INSTALL_DIR/data" \
  "$INSTALL_DIR/data/mongo" \
  "$INSTALL_DIR/logs" \
  "$INSTALL_DIR/backups"
success "Ownership set to ${SERVICE_USER}"

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

# ── Create systemd service ────────────────────────────────────────
info "Creating systemd service..."

cat > /etc/systemd/system/zoey.service << EOF
[Unit]
Description=Zoey AI Assistant — Graystone Solutions
Documentation=https://gitlab.com/graystone-solutions/zoey
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=${SERVICE_USER}
Group=docker
WorkingDirectory=${INSTALL_DIR}

# Start the stack
ExecStart=/usr/bin/docker compose -f ${INSTALL_DIR}/zoey_docker-compose.yml up -d --build

# Stop the stack
ExecStop=/usr/bin/docker compose -f ${INSTALL_DIR}/zoey_docker-compose.yml down

# Restart policy
Restart=on-failure
RestartSec=10s

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=zoey

# Security hardening
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=${INSTALL_DIR}

[Install]
WantedBy=multi-user.target
EOF

success "systemd unit file written to /etc/systemd/system/zoey.service"

# ── Reload systemd and enable service ────────────────────────────
info "Reloading systemd daemon..."
systemctl daemon-reload
success "systemd daemon reloaded"

info "Enabling Zoey service to start on boot..."
systemctl enable zoey.service
success "Zoey service enabled"

# ── Offer to start the service now ───────────────────────────────
echo ""
read -rp "  Start Zoey now? [Y/n]: " start_confirm
if [[ "${start_confirm,,}" != "n" ]]; then
  info "Starting Zoey..."
  systemctl start zoey.service
  sleep 3
  if systemctl is-active --quiet zoey.service; then
    success "Zoey is running"
  else
    warn "Zoey may not have started cleanly. Check status with:"
    warn "  systemctl status zoey.service"
    warn "  journalctl -u zoey.service -f"
  fi
else
  info "Skipped. Start Zoey manually when ready:"
  info "  systemctl start zoey.service"
fi

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
echo -e "  ${CYAN}1.${NC}  Start Zoey:      ${BOLD}systemctl start zoey.service      # start${NC}"
echo -e "  ${CYAN}2.${NC}  Stop Zoey:      ${BOLD}systemctl stop zoey.service       # stop${NC}"
echo -e "  ${CYAN}3.${NC}  Restart Zoey:      ${BOLD}systemctl restart zoey.service    # restart${NC}"
echo -e "  ${CYAN}4.${NC}  Check Status:      ${BOLD}systemctl status zoey.service     # health check${NC}"
echo -e "  ${CYAN}5.${NC}  View Logs:      ${BOLD}journalctl -u zoey.service -f     # live logs${NC}"

echo ""
