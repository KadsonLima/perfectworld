#!/bin/sh
set -eu
cd /home
./gs gs01 gs.conf gmserver.conf gsalias.conf bg01 bg02 bg03 bg04 bg05 bg06

# gs launches the world processes and then exits; keep their container alive.
trap 'killall gs 2>/dev/null || true; exit 0' TERM INT
while pidof gs >/dev/null 2>&1; do
    sleep 2 &
    wait $! || true
done
exit 1
