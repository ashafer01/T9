#!/bin/sh

## Remove all local Docker images

docker images -f label=t9.image --format '{{.ID}}' | xargs docker rmi
