# standalone Orchestration

This orchestration is meant for running T9 and an exec container only, and
connecting to an existing IRC server and Postgres database.

Also intend as the starting point for anyone who was running T9 prior to 0.2.0
(without the exec server).

## Images

T9 images are not presently pushed to any public Docker repo.

Run `./build-images.sh` in the root of this Git repo to build all images
and give them the expected local tags.

`./clean-images.sh` will destroy all local T9 images.

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

## Database

The example compose file assumes you have a container named `postgres` running
which in turn is set up with users and permissions as appropriate, and the
[schema](../../schema) has been loaded (the `postgres` name is used in the
`external_links:` sections in both service definitions)

In order for the example compose file to work, you must connect the postgres container
to the network created by the compose file.

```bash
# create everything but dont start anything
docker-compose up --no-start

# connect the postgres container to the compose-created network
# The network name will be prefixed with the directory name where you ran compose
docker network connect standalone_default postgres

# If you're not sure about the name of the network (or if the above fails), run:
docker network ls
# The correct network should be the last one listed if you are the only user of this
# Docker host and not running anything else. Use its name in place of
# "standalone_default" in the previous command
```

For the record, the majority of T9 works without a database (nothing will persist
other than what is stored on the home volume though). You can remove the `db:`
section from your config to run in-memory only.

## IRC connection

For most internet-connected IRC servers you can just point your T9 config at their
hostname and everything will work normally.

For IRC servers running on the local Docker host, you can add another
`external_links:` entry and connect the container to the compose network (see example
for database above).

For me it was convenient to create another container that creates an SSH tunnel to the
IRC server and then exposes the tunnel port on the compose network.

```dockerfile
FROM alpine

# Generate keys:
#   ssh-keygen -t ecdsa
# To generate a known_hosts I suggest SSH'ing to the IRC server from a clean image
# and manually validating and accepting the host key, then copying the created
# known_hosts to the build context. This only needs to be done once per host.
COPY t9_id_ecdsa t9_id_ecdsa.pub known_hosts /root/

RUN apk --no-cache add openssh-client
EXPOSE 45556

CMD ssh -v -i /root/t9_id_ecdsa -o UserKnownHostsFile=/root/known_hosts -L 0.0.0.0:45556:127.0.0.1:6667 -N irc-tunnel@irc-host.example.org
```

```yaml
# ...
services:
  # ...
  irc-tunnel:
    container_name: irc-tunnel
    hostname: irc-tunnel
    image: my-irc-tunnel
    restart: unless-stopped
    # Above Dockerfile gets put in this dir along with keys and known_hosts
    build: ./tunnel-image
  t9-irc-bot:
    # ...
    depends:
      - t9-exec-server
      - irc-tunnel
```

## Configuration

Start by making a copy of the example config:

```bash
cp ../../example-config.yaml config.yaml
```

Edit with the editor of your choice. Ensure `host` and `port` are set correctly for your IRC connection. If the
server uses a connection password, set `password` (this is different from a NickServ password; connection passwords
are less common).

The parameters under `db:` will get passed through as keywords arguments to
[psycopg2.connect](http://initd.org/psycopg/docs/module.html#psycopg2.connect) and should be appropriate to your
database configuration. If using the default `external_links:` in the compose file, `db.host` should be `postgres`.

If user functions need database access, ensure the `user_db:` section is configured appropriately. Keys within this
section will get built into a libpq DSN string and passed in via environment variables.

Everything else in the example should work as a good default.

After you have it set up, copy it to the container/volume:

```bash
docker cp config.yaml t9-irc-bot:/etc/t9/config.yaml
```

## Start!

```bash
docker-compose up
```
