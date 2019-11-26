#!/bin/bash

## Quickly bring up a local T9 stack

set -e

compose_file="orchestration/quickstart/docker-compose.yaml"

./build-images.sh

docker-compose -f "$compose_file" up --no-start
docker cp example-config.yaml t9-irc-bot:/etc/t9/config.yaml
docker-compose -f "$compose_file" up -d postgres
sleep 5
cat schema/*.sql | docker exec -i t9-postgres psql -U postgres
docker-compose -f "$compose_file" up
