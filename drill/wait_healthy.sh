#!/usr/bin/env bash
# Wait up to 180 s for the sovkit Nextcloud container to report healthy.
for _ in $(seq 1 90); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' sovkit-nextcloud 2>/dev/null)" = healthy ] && { echo healthy; exit 0; }
  sleep 2
done
echo "timeout: sovkit-nextcloud not healthy after 180 s" >&2; exit 1
