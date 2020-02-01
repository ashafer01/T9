#!/bin/bash

## Destroy the T9 stack created by quickstart.sh

set -e

compose_file="orchestration/quickstart/docker-compose.yaml"

docker-compose -f "$compose_file" down -v
