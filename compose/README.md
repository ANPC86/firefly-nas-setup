# Compose files

Two stacks, deployed in this order on the same Docker host.

| Folder | What it runs | Publishes |
|---|---|---|
| [`firefly/`](firefly/) | Firefly III 6.6.6, MariaDB 11.4 LTS, the Data Importer 2.3.4, a cron caller, and an opt-in daily dump sidecar | `8080` (Firefly), `8081` (importer) |
| [`firefly-mcp/`](firefly-mcp/) | [daften/fireflyiii-mcp](https://github.com/daften/fireflyiii-mcp) for **one** Firefly user, HTTP transport, read-only by default | `8490` |

Each folder has a `.env.example`; copy it to `.env`, fill in the placeholders, and keep `.env` out of version control (the root `.gitignore` already ignores it).

```bash
cd compose/firefly && cp .env.example .env && $EDITOR .env
docker compose --profile backup up -d        # drop --profile backup if you do not want the dump sidecar
curl -f http://localhost:8080/health         # OK

# ...log in once, create a Personal Access Token, put it in .env, then:
docker compose up -d importer

cd ../firefly-mcp && cp .env.example .env && $EDITOR .env
docker compose up -d
curl -f http://localhost:8490/health
```

Notes that cost time when missed:

- **`APP_KEY` is forever.** It encrypts fields in the database. Generate a real 32-character value before the first start; changing it later loses access to whatever was encrypted with the old one.
- **The cron caller is not optional.** Firefly has no internal scheduler. Recurring transactions, auto-budget limits, bill warnings and webhooks fire only when `/api/v1/cron/<token>` is called. The reference install ran for five months with budgets configured and no limits ever created, because nothing was calling it. The `cron` service here does; if you replace it with your own scheduler, verify afterwards that `configuration.last_ab_job` advances.
- **The importer needs a token that does not exist yet on first start.** The container comes up and complains until `FIREFLY_III_ACCESS_TOKEN` is set. That is expected; fill it in after your first login and restart only the importer.
- **`VANITY_URL` vs `FIREFLY_III_URL`.** The importer talks to the core over the container network (`http://app:8080`), but the links it renders must be reachable by your browser. If they are not, "Authenticate" loops back to an unreachable host.
- **Pin the tags.** The importer tracks the core's API; the MCP server reads the same API. Exclude these containers from any auto-update feature and move all three together.
- **MariaDB, not the example's.** Upstream's compose uses a MariaDB image too; this one pins the 11.4 LTS line and uses `MYSQL_RANDOM_ROOT_PASSWORD` so no root credential exists anywhere. The client binary inside the container is `mariadb`, not `mysql`.
- **Backups** land in `compose/firefly/backups/daily/` as `firefly-latest.sql.gz` plus dated copies. Put that path on a different disk than `./db`. Take one manually (`docker exec firefly_iii_backup /backup.sh`) before any batch write.
- **Ports.** Check the host before choosing one: `ss -ltn | grep :8490` and `docker ps --format '{{.Ports}}'` together. A port a NAS app already holds fails the container's start with "port is already allocated".
- **One MCP server per Firefly user.** The server holds one token, so it represents one user. Name each registration after the user.
