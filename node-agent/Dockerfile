FROM python:3.12-slim

LABEL maintainer="VodkinNET"
LABEL description="AWG-RT node-agent — manages one AmneziaWG container via Docker socket"

WORKDIR /app

# No AmneziaWG tooling is installed here on purpose — this container
# never touches WireGuard state directly. All `awg`/`awg-quick` calls
# happen via docker exec into the separate amnezia-awg2 container
# (see src/docker_control/executor.py). Keeping this image minimal
# also means it doesn't need --privileged or NET_ADMIN at all.

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Runs as a non-root user inside its own container. Note this does NOT
# reduce the Docker-socket risk described in docker_control/executor.py
# — access to the socket is host-root-equivalent regardless of the
# uid running inside this container — but it's good hygiene against
# any unrelated in-container vulnerability.
RUN useradd --create-home --shell /bin/false agent
USER agent

EXPOSE 8181

# Always bind 0.0.0.0 *inside* the container — the actual host-level
# exposure is controlled by docker-compose's port mapping
# (127.0.0.1:8181:8181), not by this bind address. LISTEN_HOST in
# Settings exists for a possible future non-Docker deployment and is
# intentionally not used here.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8181"]
