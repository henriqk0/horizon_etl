#!/bin/sh
set -e

USER_UID=${USER_UID:-1000}
USER_GID=${USER_GID:-1000}

for dir in /app/data/lattes_json /app/data/raw /app/data/exports /app/cache /app/logs /app/db /tmp/prefect; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
    fi
    chown -R "$USER_UID:$USER_GID" "$dir"
done

exec gosu "$USER_UID:$USER_GID" "$@"
