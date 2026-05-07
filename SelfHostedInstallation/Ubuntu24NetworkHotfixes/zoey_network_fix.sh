#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Zoey Network Fix — Biggerbrain
#  Fixes Docker 29.x nftables rules that don't get programmed
#  automatically for new bridge networks on Ubuntu 24.04
#
#  Run once after docker compose up, or install as a systemd
#  service to run automatically on boot after Docker starts.
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

[[ $EUID -ne 0 ]] && die "Run as root: sudo $0"

# ── Wait for Docker to be ready ───────────────────────────────────────────────
info "Waiting for Docker..."
for i in {1..10}; do
    docker info &>/dev/null && break
    sleep 2
done
docker info &>/dev/null || die "Docker not running"
success "Docker is ready"

# ── Wait for zoey_zoeynet to exist ───────────────────────────────────────────
info "Waiting for zoey_zoeynet..."
for i in {1..20}; do
    BRIDGE=$(docker network inspect zoey_zoeynet \
        --format='{{index .Options "com.docker.network.bridge.name"}}' 2>/dev/null || true)
    [[ -n "$BRIDGE" ]] && break
    sleep 2
done

# If Docker didn't name the bridge, find it from the network ID
if [[ -z "$BRIDGE" ]]; then
    NET_ID=$(docker network inspect zoey_zoeynet --format='{{.Id}}' 2>/dev/null || true)
    [[ -z "$NET_ID" ]] && die "zoey_zoeynet not found. Is the stack running?"
    BRIDGE="br-${NET_ID:0:12}"
fi

info "zoey_zoeynet bridge: ${BRIDGE}"

# ── Verify bridge exists on the host ─────────────────────────────────────────
ip link show "$BRIDGE" &>/dev/null || die "Bridge interface $BRIDGE not found on host"
success "Bridge interface confirmed"

# ── Get zoey subnet ───────────────────────────────────────────────────────────
SUBNET=$(docker network inspect zoey_zoeynet \
    --format='{{range .IPAM.Config}}{{.Subnet}}{{end}}')
[[ -z "$SUBNET" ]] && die "Could not determine zoey_zoeynet subnet"
info "zoey subnet: ${SUBNET}"

# ── Apply nftables rules ──────────────────────────────────────────────────────
info "Applying nftables rules..."

# Inter-container traffic (zoeycore <-> zoeydb)
nft add rule ip filter DOCKER-FORWARD \
    iifname "$BRIDGE" oifname "$BRIDGE" counter accept 2>/dev/null \
    && success "Inter-container FORWARD rule added" \
    || warn "Inter-container FORWARD rule may already exist"

# Established connections back into the network
nft add rule ip filter DOCKER-CT \
    oifname "$BRIDGE" ct state related,established counter accept 2>/dev/null \
    && success "DOCKER-CT established rule added" \
    || warn "DOCKER-CT rule may already exist"

# Outbound internet from containers
nft add rule ip filter FORWARD \
    iifname "$BRIDGE" oifname "eth0" counter accept 2>/dev/null \
    && success "Outbound FORWARD rule added" \
    || warn "Outbound FORWARD rule may already exist"

# Return traffic from internet
nft add rule ip filter FORWARD \
    iifname "eth0" oifname "$BRIDGE" ct state related,established counter accept 2>/dev/null \
    && success "Return FORWARD rule added" \
    || warn "Return FORWARD rule may already exist"

# NAT masquerade for outbound traffic
nft add rule ip nat POSTROUTING \
    ip saddr "$SUBNET" oifname != "$BRIDGE" masquerade 2>/dev/null \
    && success "NAT masquerade rule added" \
    || warn "NAT masquerade rule may already exist"

# ── Verify connectivity ───────────────────────────────────────────────────────
info "Testing inter-container connectivity..."
sleep 2

ZOEYCORE=$(docker ps --filter "name=zoeycore" --format "{{.Names}}" | head -1)
if [[ -n "$ZOEYCORE" ]]; then
    if docker exec "$ZOEYCORE" python3 -c \
        "import socket; s=socket.socket(); s.settimeout(3); s.connect(('zoeydb',27017)); print('ok')" \
        2>/dev/null | grep -q ok; then
        success "zoeycore -> zoeydb: connected"
    else
        warn "zoeycore -> zoeydb: still not reachable — check manually"
    fi

    info "Testing internet connectivity..."
    if docker exec "$ZOEYCORE" python3 -c \
        "import socket; s=socket.socket(); s.settimeout(3); s.connect(('8.8.8.8',53)); print('ok')" \
        2>/dev/null | grep -q ok; then
        success "zoeycore -> internet: reachable"
    else
        warn "zoeycore -> internet: not reachable — check manually"
    fi
else
    warn "zoeycore container not found — start the stack first to verify"
fi

echo ""
success "Network fix complete"
