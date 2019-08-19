#!/bin/bash
# Example `docker run` script for T9

host_mount="/media/t9-home-mnt"

# the --name must match `container_name` in config.yaml
# tune resource contraints as you see appropriate
docker run -d --name t9-exec \
  -m 1g \
  --cpus 0.75 \
  --ulimit nofile=1000:3000 \
  --ulimit nproc=200:600 \
  -v "$host_mount:/home" \
  --restart unless-stopped \
  t9-exec
