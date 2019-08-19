# T9 Docker setup

T9 uses a shared persistent docker container to run user functions.

The following instructions assume Linux and will need to be modified for other
host operating systems.

1. Build the image

```
cd build
./build.sh
```

2. Set up /home volume

Typically you will want to create a volume to mount as `/home` on the container.
I use a fixed-size block file for my `/home` filesystem to ensure the size
stays fixed. You can create and mount this like so:

```
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

Alternatively you can just create a directory for docker to use with the
volume mount. This may allow unrestrained use of the space on the host
filesystem by the docker container.

```
mkdir /media/t9-home-mnt
```

3. Set up run.sh

```
cp example-run.sh run.sh
```

If you followed the examples above exactly, no modification is needed.

Otherwise, edit to include the path you set up in step 2 for the `host_mount`
variable.

4. Run the container

```
./run.sh
```

By default the container will re-run when the docker host starts unless you
have manually stopped it with `docker stop t9-exec`.
