#!/usr/bin/env sh
set -eu

repository_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
compose_file="$repository_root/compose.demo.yaml"
demo_password="${DEMO_OWNER_PASSWORD:-SyntheticDemoOnly!2026}"
http_port="${HTTP_PORT:-8080}"
base_url="http://127.0.0.1:$http_port"
demo_origin="${DEMO_ORIGIN:-http://localhost:$http_port}"

cd "$repository_root"
docker compose -f "$compose_file" config --quiet
docker compose -f "$compose_file" up -d --build db
docker compose -f "$compose_file" run --rm migrate
docker compose -f "$compose_file" --profile reset run --rm seed
docker compose -f "$compose_file" up -d --build api worker frontend

attempt=0
until curl --fail --silent --show-error "$base_url/healthz" >/dev/null &&
  curl --fail --silent --show-error "$base_url/api/v1/health/ready" >/dev/null; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    docker compose -f "$compose_file" ps
    docker compose -f "$compose_file" logs --no-color api frontend
    echo "Demo services did not become healthy." >&2
    exit 1
  fi
  sleep 2
done

docker compose -f "$compose_file" exec -T api \
  /app/.venv/bin/python -m app.cli.verify_demo \
  --base-url http://frontend/api/v1 \
  --origin "$demo_origin" \
  --password "$demo_password"

docker compose -f "$compose_file" restart api frontend
attempt=0
until curl --fail --silent --show-error "$base_url/api/v1/health/ready" >/dev/null; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "Demo services did not recover after restart." >&2
    exit 1
  fi
  sleep 2
done

docker compose -f "$compose_file" exec -T api \
  /app/.venv/bin/python -m app.cli.verify_demo \
  --base-url http://frontend/api/v1 \
  --origin "$demo_origin" \
  --password "$demo_password" \
  --skip-pdf

docker compose -f "$compose_file" exec -T api \
  /app/.venv/bin/python -m app.cli.verify_restore

printf '%s\n' '{"status":"passed","checks":["seed","api","pdf","restart","persistence","restore-invariants"]}'
