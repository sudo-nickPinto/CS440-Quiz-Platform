# Docker and Reclaim deployment

The deployment runs two public-application containers:

- `frontend`: builds the React app, serves it with Caddy, terminates HTTPS, and
  proxies API and WebSocket traffic to the backend.
- `backend`: runs one FastAPI/Uvicorn worker on the private Docker network.

MySQL can be either a separate Reclaim database node or the optional persistent
MySQL container in `compose.mysql.yaml`. Only the frontend publishes a host
port; the backend and database stay private.

## Why the backend uses one worker

The current live-session connection hub and timers live in process memory.
Multiple Uvicorn workers would each have a different connection registry and
could send inconsistent WebSocket events. Keep one backend worker until the hub
uses shared pub/sub and scheduling infrastructure such as Redis.

## Configuration

Create the deployment environment file from the example:

```bash
cp deploy/.env.example deploy/.env
```

Fill in Auth0 and database values. `deploy/.env` is ignored by Git and must not
be committed. The React `VITE_*` values are compiled into its image, so rebuild
the frontend after changing Auth0 values. Database credentials are supplied to
the backend only at runtime and are not stored in either image.

For the deployed URL, configure Auth0 with:

- Allowed Callback URLs: `https://YOUR-DOMAIN`
- Allowed Logout URLs: `https://YOUR-DOMAIN`
- Allowed Web Origins: `https://YOUR-DOMAIN`

Set `CORS_ORIGINS=https://YOUR-DOMAIN` as well. Normal browser API calls are
same-origin through `/api`, but this keeps direct API access correctly scoped.

Set `APP_SITE_ADDRESS` to the public hostname without a scheme. Caddy obtains
and renews its certificate automatically. Ports 80 and 443 must reach the
Docker host so the ACME challenge and HTTPS traffic can succeed:

```dotenv
APP_PORT=80
APP_HTTPS_PORT=443
APP_SITE_ADDRESS=quizburg.us.reclaim.cloud
CORS_ORIGINS=https://quizburg.us.reclaim.cloud
```

## Local full-stack verification

To run the app plus a new persistent MySQL database:

```bash
docker compose \
  --env-file deploy/.env \
  -f compose.yaml \
  -f compose.mysql.yaml \
  up --build -d
```

For local use, keep `APP_SITE_ADDRESS=http://localhost` and open
`http://localhost:8080`. Check container and application health with:

```bash
docker compose \
  --env-file deploy/.env \
  -f compose.yaml \
  -f compose.mysql.yaml \
  ps

curl http://localhost:8080/healthz
curl http://localhost:8080/api/health
```

The five SQL migrations are applied by MySQL only when `mysql-data` is first
created. Restarting the containers does not re-run them and does not erase data.

Stop the stack without deleting its database:

```bash
docker compose \
  --env-file deploy/.env \
  -f compose.yaml \
  -f compose.mysql.yaml \
  down
```

Do not add `--volumes` unless intentionally deleting the Docker-hosted database.

## Reclaim with a separate MySQL node

1. Create the MySQL node/database in the same Reclaim private environment.
2. Apply every `ulugbek-err/migrations/*.up.sql` file in numeric order once.
3. Set `DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USERNAME`, and `DB_PASSWORD` in
   `deploy/.env` to the node's private connection details.
4. Build and start only the application stack:

```bash
docker compose --env-file deploy/.env up --build -d
```

## Reclaim with Docker-hosted MySQL

On a Reclaim Docker Engine node, clone the repository and use the overlay:

```bash
docker compose \
  --env-file deploy/.env \
  -f compose.yaml \
  -f compose.mysql.yaml \
  up --build -d
```

Set `APP_PORT=80`, `APP_HTTPS_PORT=443`, and `APP_SITE_ADDRESS` to the Reclaim
hostname. Keep the `mysql-data` and `caddy-data` volumes and arrange database
backups before entering real course data.

Reclaim accepts environment variables, private container networking, volumes,
and exposed ports for custom Docker deployments. Its shared load balancer can
serve common web ports; other public ports require an endpoint or public IP.

## Updating

After pulling new code, rebuild the images and recreate changed containers:

```bash
git pull --ff-only
docker compose --env-file deploy/.env up --build -d
```

If MySQL is running through the overlay, include both `-f` arguments in every
Compose command. New migrations must be applied explicitly to an existing
database because `/docker-entrypoint-initdb.d` only initializes an empty volume.
