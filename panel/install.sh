#!/usr/bin/env bash
#
# Installs the AWG-RT panel: postgres + redis + the panel app itself,
# running under a dedicated service account instead of root.
#
# Run this ON THE MAIN SERVER, from inside the panel/ directory of a
# freshly cloned repo:
#
#   cd Vodkinnet-AWG-RT/panel
#   sudo ./install.sh
#
# What this does to your system, in order:
#   1. Installs Docker if missing
#   2. Creates a dedicated system account (default: awgrt) with no
#      login shell, and adds it to the `docker` group
#   3. Copies the panel's files into /opt/vodkinnet-awg-rt, owned by
#      that account
#   4. Generates secrets and starts postgres+redis+panel — all
#      docker compose commands from this point run AS the service
#      account (via `sudo -u`), never as root
#
# Safe to re-run: if an install already exists at INSTALL_DIR, its
# .env is reused as-is — regenerating POSTGRES_PASSWORD or JWT_SECRET
# on an existing install would lock the panel out of its own database
# and invalidate every admin's session, so this script never does
# that automatically.
#
# IMPORTANT — read before assuming this is a hard security boundary:
# membership in the `docker` group is functionally equivalent to root
# on the host (a container can bind-mount the host's root filesystem).
# This service account does NOT sandbox the panel from a determined
# attacker who already has a shell as that account. What it DOES give
# you: no interactive root login for routine panel operations, files
# and secrets owned by a narrowly-named account instead of root, and
# isolation from unrelated root-level cron jobs/scripts that might
# otherwise touch panel files by accident. It's separation of
# duties, not a jail.

set -euo pipefail

SERVICE_USER="${AWGRT_SERVICE_USER:-awgrt}"
INSTALL_DIR="${AWGRT_INSTALL_DIR:-/opt/vodkinnet-awg-rt}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()  { echo -e "\033[1;34m[install-panel]\033[0m $*"; }
warn() { echo -e "\033[1;33m[install-panel]\033[0m $*"; }
err()  { echo -e "\033[1;31m[install-panel]\033[0m $*" >&2; }

# Runs a command as the service account, with a real bash regardless
# of that account's own (nologin) shell — `sudo -u` execs the given
# command directly, it doesn't require the target account to have an
# interactive-capable shell.
as_service_user() {
    sudo -u "$SERVICE_USER" -H bash -c "$1"
}

# --- 1. Root check -----------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    err "This script must be run as root (or with sudo)."
    exit 1
fi

# --- 2. Docker + Compose plugin check/install ---------------------------------
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

# --- 3. Service account -------------------------------------------------------
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

# --- 4. Copy application files into the canonical install location -----------
mkdir -p "$INSTALL_DIR"

if [ -f "$INSTALL_DIR/.env" ]; then
    log "Existing installation found at $INSTALL_DIR — updating code, keeping .env."
else
    log "Fresh installation — copying files into $INSTALL_DIR."
fi

# rsync would be nicer but isn't guaranteed installed; cp -a preserves
# permissions/symlinks and is available everywhere Docker's install
# script targets. --update-safe approach: never touch an existing
# .env, always refresh everything else so re-running this script
# after a `git pull` picks up code changes.
for item in Dockerfile docker-compose.yml alembic alembic.ini requirements.txt scripts src; do
    if [ -e "$SCRIPT_DIR/$item" ]; then
        rm -rf "${INSTALL_DIR:?}/$item"
        cp -a "$SCRIPT_DIR/$item" "$INSTALL_DIR/$item"
    fi
done

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
log "Files in place at $INSTALL_DIR, owned by $SERVICE_USER."

# --- 5. .env setup -------------------------------------------------------------
if [ -f "$INSTALL_DIR/.env" ]; then
    warn ".env already exists at $INSTALL_DIR — reusing it as-is."
    warn "Skipping secret generation. If you need to rotate JWT_SECRET or"
    warn "POSTGRES_PASSWORD, do it deliberately (rotating JWT_SECRET logs"
    warn "out every admin; rotating POSTGRES_PASSWORD requires updating it"
    warn "in the running postgres container too) — this script won't do"
    warn "that for you automatically to avoid a surprise lockout."
else
    log "Generating .env with fresh secrets."

    GENERATED_PG_PASSWORD="$(openssl rand -hex 24)"
    GENERATED_JWT_SECRET="$(openssl rand -hex 32)"

    # DATABASE_URL is written out with the real password inlined —
    # .env files are NOT shell scripts, so ${POSTGRES_PASSWORD}-style
    # interpolation inside the file would NOT be expanded by the
    # Python app reading it (pydantic-settings reads .env as flat
    # key=value pairs, no variable substitution). Docker Compose DOES
    # do its own ${VAR} substitution for values used directly in
    # docker-compose.yml, which is a separate mechanism from what the
    # app sees — hence writing the password twice here, deliberately.
    cat > "$INSTALL_DIR/.env" << EOF
# Generated by install.sh on $(date -u +"%Y-%m-%dT%H:%M:%SZ")

POSTGRES_USER=awgrt
POSTGRES_PASSWORD=${GENERATED_PG_PASSWORD}
POSTGRES_DB=awgrt
DATABASE_URL=postgresql+asyncpg://awgrt:${GENERATED_PG_PASSWORD}@postgres:5432/awgrt

REDIS_URL=redis://redis:6379/0
PEER_CONFIG_TTL_SECONDS=172800

JWT_SECRET=${GENERATED_JWT_SECRET}

MONITORING_INTERVAL_SECONDS=180
HANDSHAKE_STALE_AFTER_SECONDS=300
HANDSHAKE_DOWN_AFTER_SECONDS=900

LOG_LEVEL=INFO
APP_ENV=production
EOF

    chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
    log ".env created (permissions 600, owned by $SERVICE_USER)."
fi

# --- 6. Build and start, all as the service account ---------------------------
log "Building the panel image (as $SERVICE_USER)..."
as_service_user "cd '$INSTALL_DIR' && docker compose build"

log "Starting postgres and redis..."
as_service_user "cd '$INSTALL_DIR' && docker compose up -d --remove-orphans postgres redis"

log "Waiting for postgres to become healthy..."
PG_STATUS="starting"
for _ in $(seq 1 30); do
    PG_STATUS="$(docker inspect --format='{{.State.Health.Status}}' awgrt-postgres 2>/dev/null || echo "starting")"
    if [ "$PG_STATUS" = "healthy" ]; then
        break
    fi
    sleep 2
done
if [ "$PG_STATUS" != "healthy" ]; then
    err "postgres did not become healthy in time. Check:"
    err "  sudo -u $SERVICE_USER docker compose -f $INSTALL_DIR/docker-compose.yml logs postgres"
    exit 1
fi
log "postgres is healthy."

log "Starting the panel (this also runs 'alembic upgrade head' on boot)..."
as_service_user "cd '$INSTALL_DIR' && docker compose up -d --remove-orphans panel"

log "Cleaning up dangling images left over from previous builds..."
IMAGES_PRUNED="$(as_service_user "docker image prune -f" 2>&1)"
log "$IMAGES_PRUNED"

log "Waiting for the panel to respond..."
HEALTHY=0
for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:8000/docs" > /dev/null 2>&1; then
        HEALTHY=1
        break
    fi
    sleep 2
done

if [ "$HEALTHY" -ne 1 ]; then
    err "Panel did not respond within 60 seconds. Check:"
    err "  sudo -u $SERVICE_USER docker compose -f $INSTALL_DIR/docker-compose.yml logs panel"
    exit 1
fi
log "Panel is up and responding on 127.0.0.1:8000."

# --- 7. First admin account ----------------------------------------------------
echo ""
read -rp "Create the first admin account now? [Y/n] " CREATE_ADMIN_ANSWER
CREATE_ADMIN_ANSWER="${CREATE_ADMIN_ANSWER:-Y}"
if [[ "$CREATE_ADMIN_ANSWER" =~ ^[Yy] ]]; then
    as_service_user "cd '$INSTALL_DIR' && docker compose exec panel python3 scripts/create_admin.py"
else
    log "Skipped. Create one later with:"
    log "  sudo -u $SERVICE_USER docker compose -f $INSTALL_DIR/docker-compose.yml exec panel python3 scripts/create_admin.py"
fi

# --- 8. Final instructions --------------------------------------------------
echo ""
log "Panel installation complete."
echo ""
echo "  Installed at: $INSTALL_DIR (owned by '$SERVICE_USER')"
echo "  The panel is listening on 127.0.0.1:8000 (localhost only) — it is"
echo "  NOT reachable from outside until you set up one of these:"
echo ""
echo "  Option A — reverse proxy with your own domain + TLS (nginx example):"
echo ""
echo "    # 1. Point a DNS A record for your chosen domain at this server's IP"
echo "    # 2. Install/confirm nginx and certbot are available, then:"
echo ""
echo "    cat > /etc/nginx/sites-available/awg-rt << 'NGINXEOF'"
echo "    server {"
echo "        listen 80;"
echo "        server_name <your-chosen-domain>;"
echo "    }"
echo "    NGINXEOF"
echo "    ln -sf /etc/nginx/sites-available/awg-rt /etc/nginx/sites-enabled/"
echo "    nginx -t && systemctl reload nginx"
echo "    certbot --nginx -d <your-chosen-domain>"
echo ""
echo "    certbot rewrites the site config to add the TLS block and a"
echo "    redirect from :80 automatically — after that, edit the"
echo "    resulting HTTPS server block's 'location /' to add:"
echo ""
echo "        proxy_pass http://127.0.0.1:8000;"
echo "        proxy_set_header Host \$host;"
echo "        proxy_set_header X-Real-IP \$remote_addr;"
echo ""
echo "    Then: nginx -t && systemctl reload nginx"
echo ""
echo "  Option B — no domain/TLS needed, SSH tunnel from your own machine:"
echo "    ssh -L 8000:127.0.0.1:8000 <user>@<this-server-ip>"
echo "    # then open http://127.0.0.1:8000 in your own browser"
echo ""
echo "  Option C — Tailscale or another private mesh VPN, if you already"
echo "  run one — install it on this host and reach 127.0.0.1:8000 over"
echo "  its private IP, still no public domain/TLS required."
echo ""
echo "  Once you've picked one, log in at https://<your-chosen-domain>/login"
echo "  (Option A) or http://127.0.0.1:8000/login (Options B/C)."
echo ""
echo "  From now on, manage the panel as '$SERVICE_USER', not root:"
echo "    sudo -u $SERVICE_USER docker compose -f $INSTALL_DIR/docker-compose.yml logs -f panel"
echo "    sudo -u $SERVICE_USER docker compose -f $INSTALL_DIR/docker-compose.yml restart panel"
echo ""
echo "  The directory you cloned this repo into is no longer needed —"
echo "  everything required now lives in $INSTALL_DIR. Safe to remove:"
echo "    rm -rf $(dirname "$SCRIPT_DIR")"
echo ""
log "To add a node, first run node-agent/install.sh on that node, then"
log "use the panel's 'Add node' form with the hostname/port/token it prints."
