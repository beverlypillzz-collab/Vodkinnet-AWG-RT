# node-agent

Internal API that lets the AWG-RT panel manage one AmneziaWG node.
Runs as its own container, separate from `amnezia-awg2`, and controls
it exclusively via the Docker socket (`docker exec`) — see
`src/docker_control/executor.py` for why this is scoped to a single,
fixed container name and never accepts one from an API request.

## Prerequisites on the node

- Nothing beyond a Debian/Ubuntu-family host with root access —
  `install.sh` installs Docker itself if it's missing, and builds
  `amnezia-awg2:2.0.0` from the bundled `amnezia-awg2/Dockerfile`.

## Setup

```bash
sudo ./install.sh
```

It creates a dedicated service account (`awgagent`, no login shell),
copies this directory's files into `/opt/vodkinnet-awg-agent` owned
by that account, prompts for the node name/port/public endpoint,
generates `.env` there, then builds and starts both containers as
`awgagent` — never as root. See `docs/deployment.md` for the full
walkthrough and the honest tradeoffs of the service-account approach.

After that, this cloned directory is no longer needed — everything
below refers to the canonical install at `/opt/vodkinnet-awg-agent`,
managed as the `awgagent` account.

## Verifying it came up correctly

```bash
sudo -u awgagent docker compose -f /opt/vodkinnet-awg-agent/docker-compose.yml ps
# both amnezia-awg2 and node-agent should show "Up"

curl -s http://127.0.0.1:8181/health | python3 -m json.tool
```

Expected:
```json
{
  "status": "ok",
  "agent_version": "1.0.0",
  "awg_container_running": true
}
```

If `awg_container_running` is `false`, the agent is up but can't see
(or reach a running state on) the `amnezia-awg2` container — see
Debugging below.

## Debugging

**Always start with logs, not guessing:**

```bash
sudo -u awgagent docker compose -f /opt/vodkinnet-awg-agent/docker-compose.yml logs -f node-agent
```

Every request gets a short correlation id (`[a1b2c3d4]`) so you can
grep one request's full trail across modules:

```bash
sudo -u awgagent docker compose -f /opt/vodkinnet-awg-agent/docker-compose.yml logs node-agent | grep a1b2c3d4
```

**Turn on verbose logging** without rebuilding — edit `/opt/vodkinnet-awg-agent/.env`:
```
LOG_LEVEL=DEBUG
```
then:
```bash
sudo -u awgagent docker compose -f /opt/vodkinnet-awg-agent/docker-compose.yml up -d node-agent
```
At `DEBUG`, every `docker exec` call into `amnezia-awg2` is logged
with its full command line — except any call that could contain key
material (`awg genkey`, config file writes), which are logged as
"output redacted" by design. If you need to verify a config file's
actual content while debugging, read it directly rather than via logs:

```bash
docker exec amnezia-awg2 cat /opt/amnezia/awg/awg0.conf
```

**Warning:** this prints the server's private key to your terminal.
Clear your scrollback and don't paste this output anywhere after
debugging.

**Common failure: `awg_container_running: false`**

```bash
# is the container actually named what .env says?
docker ps --format '{{.Names}}'
# does AWG_CONTAINER_NAME in .env match exactly?
grep AWG_CONTAINER_NAME /opt/vodkinnet-awg-agent/.env

# can the agent reach the docker socket at all?
sudo -u awgagent docker compose -f /opt/vodkinnet-awg-agent/docker-compose.yml exec node-agent python3 -c \
  "import docker; print(docker.from_env().ping())"
```

**Common failure: `/server/init` succeeds but `/server/status` shows
`interface_up: false` shortly after**

This usually means `awg-quick up` failed inside the container after
the config was written (e.g. a bad `Jc`/`Jmin`/`Jmax` combination, or
the kernel module isn't loaded). Check directly:

```bash
docker exec amnezia-awg2 awg-quick up /opt/amnezia/awg/awg0.conf
```
This will print the real error instead of the agent's already-logged
but possibly truncated version.

**Testing the API by hand** (find `$TOKEN` in `/opt/vodkinnet-awg-agent/.env`):

```bash
curl -s -X POST http://127.0.0.1:8181/server/init \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"listen_port": 55632, "awg_params": {"Jc": 4, "Jmin": 40, "Jmax": 70}}' \
  | python3 -m json.tool
```

## Running tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

Tests mock the Docker client (see `tests/conftest.py` once added) —
they do not require a real AmneziaWG container to run.

## Security notes (read before modifying `docker_control/` or `wg/`)

- The agent has `/var/run/docker.sock` mounted, which is
  host-root-equivalent. The only thing keeping this scoped is
  application-level discipline: `AWG_CONTAINER_NAME` is fixed at
  deploy time and never taken from a request. Do not change this.
- Private keys (server or client) are never logged, even at `DEBUG`.
  Functions that touch them are named explicitly and pass them via
  Docker exec's `environment` parameter rather than argv, so they
  don't show up in `ps aux` inside the container either.
- Client private keys leave this service in the `POST /peers`
  response and are the panel's responsibility from that point on —
  see the main repo's `docs/architecture.md` for how the panel handles
  them (short-TTL Redis cache, never written to Postgres).
