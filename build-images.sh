#!/bin/sh

## Build all local Docker images

set -e

echo
echo "=== Build t9-base-image ==="
echo
base_ctx="/tmp/tmp_empty_context"
rm -rf "$base_ctx"
mkdir "$base_ctx"
docker build -t t9-base-image -f Dockerfile.t9-base-image "$base_ctx"
rmdir "$base_ctx"

echo
echo "=== Build t9-exec-server ==="
echo
docker build -t t9-exec-server -f Dockerfile.t9-exec-server .

echo
echo "=== Build t9-irc-bot ==="
echo
docker build -t t9-irc-bot -f Dockerfile.t9-irc-bot .
