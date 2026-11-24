#!/bin/bash
set -euo pipefail

: "${IMAGE:?Set IMAGE to the candidate image}"
: "${VERSION:?Set VERSION to the OHC release tag}"
: "${RESOLUTION:?Set RESOLUTION to the expected display size}"
: "${PLATFORM:?Set PLATFORM to the target platform}"
mkdir -p smoke-artifacts

container=$(docker create --platform "$PLATFORM" -p 127.0.0.1::8080 -p 127.0.0.1::8081 "$IMAGE")
cleanup() {
    docker logs "$container" > smoke-artifacts/stdout.log 2>&1 || true
    docker rm -f -v "$container" > /dev/null || true
}
trap cleanup EXIT
docker start "$container" > /dev/null
api_port=$(docker port "$container" 8080/tcp | sed 's/.*://')
ui_port=$(docker port "$container" 8081/tcp | sed 's/.*://')

for _ in $(seq 1 120); do
    if curl -fsS --max-time 3 "http://127.0.0.1:$ui_port/live.html" > smoke-artifacts/live.html 2>/dev/null; then
        break
    fi
    if [ "$(docker inspect -f '{{.State.Running}}' "$container")" != true ]; then
        echo "Container exited before UI became ready" >&2
        exit 1
    fi
    sleep 5
done
if [ ! -s smoke-artifacts/live.html ]; then
    echo "UI did not become ready" >&2
    exit 1
fi
if [ -n "${PLAYWRIGHT_NODE_PATH:-}" ]; then
    for _ in $(seq 1 120); do
        docker logs "$container" > smoke-artifacts/startup.log 2>&1
        if grep -q 'Setup: running' smoke-artifacts/startup.log; then break; fi
        if [ "$(docker inspect -f '{{.State.Running}}' "$container")" != true ]; then
            echo "Container exited before setup" >&2
            exit 1
        fi
        sleep 5
    done
    if ! grep -q 'Setup: running' smoke-artifacts/startup.log; then
        echo "First-run setup did not become ready" >&2
        exit 1
    fi
    NODE_PATH="$PLAYWRIGHT_NODE_PATH" node scripts/screenshot.js "http://127.0.0.1:$ui_port/live.html" setup
else
    echo "Playwright unavailable; first-run setup requires manual completion" >&2
fi

wait_for_api() {
    for _ in $(seq 1 120); do
        if curl -fsS --max-time 3 "http://127.0.0.1:$api_port/get_sys.txt" > smoke-artifacts/sys.txt 2>/dev/null; then
            return 0
        fi
        if [ "$(docker inspect -f '{{.State.Running}}' "$container")" != true ]; then
            echo "Container exited before API became ready" >&2
            return 1
        fi
        sleep 5
    done
    echo "API did not become ready" >&2
    return 1
}

wait_for_api
app_version=${VERSION#v}
app_version=${app_version%.*}
width=${RESOLUTION%x*}
height=${RESOLUTION#*x}
grep -Eq "^Version[[:space:]]+$app_version[[:space:]]*$" smoke-artifacts/sys.txt
grep -Eq "^BuildSz[[:space:]]+$width x $height[[:space:]]*$" smoke-artifacts/sys.txt
grep -Eq '^BEHost[[:space:]]+ohb\.hamclock\.app[[:space:]]*$' smoke-artifacts/sys.txt
grep -Eq '^BEPort[[:space:]]+80[[:space:]]*$' smoke-artifacts/sys.txt
curl -fsS --max-time 10 "http://127.0.0.1:$ui_port/live.html" > smoke-artifacts/live.html
if [ -n "${PLAYWRIGHT_NODE_PATH:-}" ]; then
    for _ in $(seq 1 120); do
        docker logs "$container" > smoke-artifacts/startup.log 2>&1
        if grep -q 'Starting Arduino loop()' smoke-artifacts/startup.log; then break; fi
        sleep 5
    done
    if ! grep -q 'Starting Arduino loop()' smoke-artifacts/startup.log; then
        echo "Main loop did not start" >&2
        exit 1
    fi
    NODE_PATH="$PLAYWRIGHT_NODE_PATH" node scripts/screenshot.js "http://127.0.0.1:$ui_port/live.html"
fi
docker restart "$container" > /dev/null
api_port=$(docker port "$container" 8080/tcp | sed 's/.*://')
wait_for_api
curl -fsS --max-time 10 "http://127.0.0.1:$api_port/get_de.txt" > smoke-artifacts/de.txt
grep -Eq '^Call[[:space:]]+N0CAL[[:space:]]*$' smoke-artifacts/de.txt
