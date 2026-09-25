#!/bin/sh
set -eu
cd "$(dirname "$0")"
docker info >/dev/null
docker compose ps -a
ids=$(docker compose ps -q)
if [ -n "$ids" ]; then docker stats --no-stream $ids; fi
docker compose exec -T perfectworld-db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -h 127.0.0.1 -u root pw -e "SELECT 1 AS banco_ok; SELECT COUNT(*) AS contas FROM users;"'
docker compose logs --tail=200 2>&1 | grep -Ei 'error|fatal|failed|panic|segmentation|exception' || true
