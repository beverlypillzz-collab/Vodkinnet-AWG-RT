# node-agent

Internal API that lets the AWG-RT panel manage one AmneziaWG node.
Runs as its own container, separate from `amnezia-awg2`, and controls
it exclusively via the Docker socket (`docker exec`) — see
`src/docker_control/executor.py` for why this is scoped to a single,
fixed container name and never accepts one from an API request.

## Prerequisites on the node

- Docker + Docker Compose
- An already-built `amnezia-awg2:2.0.0` image (see the main repo's
  `docs/deployment.md` for how that image is built)

## Setup

```bash
cp .env.example .env
# generate a real token:
openssl rand -hex 32
# paste it into AGENT_TOKEN in .env, and register the same value
# for this node in the panel's "Add node" form
```

Fill in `AWG_LISTEN_PORT` to match whatever UDP port this node's
AmneziaWG server should listen on.

```bash
docker compose up -d --build
```

## Verifying it came up correctly

```bash
docker compose ps
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
docker compose logs -f node-agent
```

Every request gets a short correlation id (`[a1b2c3d4]`) so you can
grep one request's full trail across modules:

```bash
docker compose logs node-agent | grep a1b2c3d4
```

**Turn on verbose logging** without rebuilding — edit `.env`:
```
LOG_LEVEL=DEBUG
```
then:
```bash
docker compose up -d node-agent
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
grep AWG_CONTAINER_NAME .env

# can the agent reach the docker socket at all?
docker compose exec node-agent python3 -c \
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

**Testing the API by hand** (replace `$TOKEN` with your real
`AGENT_TOKEN`):

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
