#!/bin/sh
set -eu
cd "$(dirname "$0")"
docker info >/dev/null
docker compose config --quiet
docker compose up -d
docker compose ps -a
