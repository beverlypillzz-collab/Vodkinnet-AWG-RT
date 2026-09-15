#!/usr/bin/env bash
#
# Installs one AWG-RT node: the amnezia-awg2 (AmneziaWG 2.0) container
# plus the node-agent that the panel talks to — running under a
# dedicated service account instead of root, same pattern as
# panel/install.sh.
#
# Run this ON THE NODE itself, from inside the node-agent/ directory
# of a freshly cloned repo:
#
#   cd Vodkinnet-AWG-RT/node-agent
#   sudo ./install.sh
#
# What this does to your system, in order:
#   1. Installs Docker if missing
#   2. Creates a dedicated system account (default: awgagent) with no
#      login shell, and adds it to the `docker` group
#   3. Copies this node's files into /opt/vodkinnet-awg-agent, owned
#      by that account
#   4. Generates secrets and starts both containers — all docker
#      compose commands from this point run AS the service account
#      via `sudo -u`, never as root
#
# Safe to re-run: if an install already exists at INSTALL_DIR, its
# .env is reused as-is — regenerating AGENT_TOKEN on an existing node
# would break its already-registered entry in the panel, so this
# script never does that automatically.
#
# IMPORTANT — read before assuming this is a hard security boundary:
# membership in the `docker` group is functionally equivalent to root
# on the host (a container can bind-mount the host's root filesystem).
# This service account does NOT sandbox the agent from a determined
# attacker who already has a shell as that account — see
# panel/install.sh's longer comment on this for the full rationale.
# It's separation of duties, not a jail.

set -euo pipefail

SERVICE_USER="${AWGRT_SERVICE_USER:-awgagent}"
INSTALL_DIR="${AWGRT_INSTALL_DIR:-/opt/vodkinnet-awg-agent}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()  { echo -e "\033[1;34m[install-node]\033[0m $*"; }
warn() { echo -e "\033[1;33m[install-node]\033[0m $*"; }
err()  { echo -e "\033[1;31m[install-node]\033[0m $*" >&2; }

as_service_user() {
    sudo -u "$SERVICE_USER" -H bash -c "$1"
}

# --- 1. Root check -----------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    err "This script must be run as root (or with sudo)."
    exit 1
fi

# --- 2. Docker + Compose plugin check/install ---------------------------
if ! command -v docker &> /dev/null; then
    log "Docker not found — installing via get.docker.com convenience script."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
else
    log "Docker already installed: $(docker --version)"
fi

if ! docker compose version &> /dev/null; then
    err "Docker is installed but the 'docker compose' plugin is missing."
    err "Reinstall via get.docker.com, or install docker-compose-plugin"
    err "manually for your distro, then re-run this script."
    exit 1
fi
log "docker compose available: $(docker compose version --short)"

# --- 3. Service account -------------------------------------------------
if id "$SERVICE_USER" &> /dev/null; then
    log "Service account '$SERVICE_USER' already exists — reusing it."
else
    log "Creating service account '$SERVICE_USER' (system account, no login shell)..."
    useradd --system --create-home --home-dir "/home/$SERVICE_USER" \
        --shell /usr/sbin/nologin "$SERVICE_USER"
fi

if ! id -nG "$SERVICE_USER" | grep -qw docker; then
    log "Adding '$SERVICE_USER' to the docker group."
    usermod -aG docker "$SERVICE_USER"
    warn "Note: docker-group membership is root-equivalent on this host"
    warn "(see the comment at the top of this script) — this is a"
    warn "deliberate, documented tradeoff, not an oversight."
else
    log "'$SERVICE_USER' is already in the docker group."
fi

# --- 4. Copy application files into the canonical install location -----
mkdir -p "$INSTALL_DIR"

if [ -f "$INSTALL_DIR/.env" ]; then
    log "Existing installation found at $INSTALL_DIR — updating code, keeping .env."
else
    log "Fresh installation — copying files into $INSTALL_DIR."
fi

for item in Dockerfile docker-compose.yml amnezia-awg2 src requirements.txt; do
    if [ -e "$SCRIPT_DIR/$item" ]; then
        rm -rf "${INSTALL_DIR:?}/$item"
        cp -a "$SCRIPT_DIR/$item" "$INSTALL_DIR/$item"
    fi
done

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
log "Files in place at $INSTALL_DIR, owned by $SERVICE_USER."

# --- 5. .env setup -------------------------------------------------------
if [ -f "$INSTALL_DIR/.env" ]; then
    warn ".env already exists at $INSTALL_DIR — reusing it as-is."
    warn "If you need to change AWG_LISTEN_PORT or regenerate AGENT_TOKEN,"
    warn "edit it by hand (it would break this node's already-registered"
    warn "entry in the panel otherwise), then re-run this script."
else
    log "No .env found — let's set one up."

    read -rp "Node name (for your own reference, e.g. my-awg-node): " NODE_NAME_INPUT
    read -rp "UDP port for AmneziaWG to listen on [55632]: " AWG_LISTEN_PORT_INPUT
    AWG_LISTEN_PORT_INPUT="${AWG_LISTEN_PORT_INPUT:-55632}"
    read -rp "Publicly reachable hostname/IP for this node (leave blank if the panel will supply it): " AWG_PUBLIC_ENDPOINT_INPUT

    GENERATED_TOKEN="$(openssl rand -hex 32)"

    cat > "$INSTALL_DIR/.env" << EOF
# Generated by install.sh on $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Node: ${NODE_NAME_INPUT}

AGENT_TOKEN=${GENERATED_TOKEN}
AWG_CONTAINER_NAME=amnezia-awg2
AWG_LISTEN_PORT=${AWG_LISTEN_PORT_INPUT}
AWG_PUBLIC_ENDPOINT=${AWG_PUBLIC_ENDPOINT_INPUT}
AWG_INTERFACE=awg0
LISTEN_HOST=0.0.0.0
LISTEN_PORT=8181
LOG_LEVEL=INFO
EOF

    chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
    log ".env created (permissions 600, owned by $SERVICE_USER)."
fi

# --- 6. Build and start, all as the service account ----------------------
log "Building images (this pulls amneziavpn/amneziawg-go:2.0.0 the first time)..."
as_service_user "cd '$INSTALL_DIR' && docker compose build"

log "Starting containers..."
as_service_user "cd '$INSTALL_DIR' && docker compose up -d --remove-orphans"

log "Cleaning up dangling images left over from previous builds..."
IMAGES_PRUNED="$(as_service_user "docker image prune -f" 2>&1)"
log "$IMAGES_PRUNED"

# --- 7. Wait for the agent to actually respond ----------------------------
log "Waiting for node-agent to become healthy..."
LISTEN_PORT_FOR_CHECK="$(grep -oP '(?<=^LISTEN_PORT=).*' "$INSTALL_DIR/.env" || echo 8181)"
AWG_LISTEN_PORT_FOR_DISPLAY="$(grep -oP '(?<=^AWG_LISTEN_PORT=).*' "$INSTALL_DIR/.env" || echo 55632)"
AGENT_TOKEN_FOR_DISPLAY="$(grep -oP '(?<=^AGENT_TOKEN=).*' "$INSTALL_DIR/.env" || echo "")"

HEALTHY=0
for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:${LISTEN_PORT_FOR_CHECK}/health" > /dev/null 2>&1; then
        HEALTHY=1
        break
    fi
    sleep 2
done

if [ "$HEALTHY" -ne 1 ]; then
    err "node-agent did not become healthy within 60 seconds."
    err "Check logs with:"
    err "  sudo -u $SERVICE_USER docker compose -f $INSTALL_DIR/docker-compose.yml logs node-agent"
    exit 1
fi

HEALTH_JSON="$(curl -fsS "http://127.0.0.1:${LISTEN_PORT_FOR_CHECK}/health")"
log "node-agent is up: ${HEALTH_JSON}"

if ! echo "$HEALTH_JSON" | grep -q '"awg_container_running": *true'; then
    warn "node-agent is reachable, but awg_container_running is not true."
    warn "Check: sudo -u $SERVICE_USER docker compose -f $INSTALL_DIR/docker-compose.yml logs amnezia-awg2"
fi

# --- 8. Final instructions -------------------------------------------------
echo ""
log "Node installation complete."
echo ""
echo "  Installed at: $INSTALL_DIR (owned by '$SERVICE_USER')"
echo ""
echo "  Add this node in the panel with:"
echo "    hostname:    $(hostname -I 2>/dev/null | awk '{print $1}' || echo '<this server'"'"'s reachable IP>')"
echo "    agent_port:  ${LISTEN_PORT_FOR_CHECK}"
echo "    listen_port: ${AWG_LISTEN_PORT_FOR_DISPLAY}"
echo "    agent_token: ${AGENT_TOKEN_FOR_DISPLAY}"
echo ""
warn "agent_token is a secret — copy it now, it will not be printed again by this script"
warn "(it is stored in $INSTALL_DIR/.env if you need it later)"
echo ""
log "Make sure port ${LISTEN_PORT_FOR_CHECK}/tcp is reachable from the panel's IP only"
log "(firewall allowlist), and port ${AWG_LISTEN_PORT_FOR_DISPLAY}/udp is open to the internet"
log "for actual VPN clients."
echo ""
echo "  From now on, manage this node as '$SERVICE_USER', not root:"
echo "    sudo -u $SERVICE_USER docker compose -f $INSTALL_DIR/docker-compose.yml logs -f node-agent"
echo "    sudo -u $SERVICE_USER docker compose -f $INSTALL_DIR/docker-compose.yml restart node-agent"
echo ""
echo "  The directory you cloned this repo into is no longer needed —"
echo "  everything required now lives in $INSTALL_DIR. Safe to remove:"
echo "    rm -rf $(dirname "$SCRIPT_DIR")"
