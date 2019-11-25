#!/bin/bash

## Quickly bring up a local T9 stack

set -e

compose_file="orchestration/quickstart/docker-compose.yaml"

./build-images.sh

docker-compose -f "$compose_file" up --no-start
docker run -it --rm \
    -v "$PWD/example-config.yaml:/tmp/example-config.yaml" \
    -v "t9-irc-bot-config:/tmp/config" \
    alpine:latest \
    cp /tmp/example-config.yaml /tmp/config/config.yaml
docker-compose -f "$compose_file" up -d postgres
sleep 5
cat schema/*.sql | docker exec -i t9-postgres psql -U postgres
docker-compose -f "$compose_file" up
