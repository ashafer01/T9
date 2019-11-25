# standalone Orchestration

This orchestration is meant for running T9 and an exec container only, and
connecting to an existing IRC server and Postgres database.

Also intend as the starting point for anyone who was running T9 prior to 0.2.0
(without the exec server).

You will most likely need to modify `docker-compose.yaml` to make use of this
orchestration.

The file assumes:

1. IRC is running on localhost. If it's in Docker, the port is published.
2. Postgres is running in Docker and is named `postgres`.
3. /media/t9-home-mnt exists

If you need to change these things, consult the docker-compose documentation.
At present they are implemented with 1) the `extra_hosts` in the bot container,
and 2) the `external_links` in both containers in the compose file

## Home Volume

In the default compose file, I use a bind mount to change the backend local
storage location. This allows me to impose a hard capacity limit as follows:

```bash
# create a 4GB block file
dd if=/dev/zero of=./home.ext4 bs=1M count=4096

# create an ext4 filesystem in it
mkfs.ext4 ./home.ext4

# create a mount point
mkdir /media/t9-home-mnt

# mount the filesystem
# NOTE: you will need to make this persistent as appropriate to your distro
[sudo] mount -t ext4 ./home.ext4 /media/t9-home-mnt
```

Alternatively you can remove `driver` and `driver_opts` from the `t9-home`
volume configuration, and Docker will create the volume using the default
storage location.
