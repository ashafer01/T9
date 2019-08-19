#!/bin/bash

# To be deployed to container, owned/executable by root, read only to everyone.
# T9 will guarantee no other user code is running on the container when
# executing this script. This prevents practical exploitation of non-atomic
# permissions changes within this script.

realpath="$(/usr/bin/realpath -e "$SECURE_BASE/$REQUESTED_LOCK" 2>&1)"

if [[ ! $? ]]; then
    first_out_line="$(echo -n "$realpath" | head -n1)"
    echo "FAILED: $first_out_line"
    exit 1
fi

if [[ "$realpath" != $SECURE_BASE/* ]]; then
    echo "FAILED: given path is not below $SECURE_BASE"
    exit 1
fi

if [[ ! -f "$realpath" ]]; then
    echo "FAILED: can only change permission on regular files"
    exit 1
fi

set -e

if [[ "$1" == "ro" ]]; then
    /bin/chown root: "$realpath"
    /bin/chmod 444 "$realpath"
    echo -n "File \"$realpath\" is now read-only. md5sum: "
    /usr/bin/md5sum "$realpath" | /usr/bin/awk '{print $1}'
elif [[ "$1" == "rw" ]]; then
    /bin/chmod 644 "$realpath"
    /bin/chown user:user "$realpath"
    echo "File \"$realpath\" is now writable"
elif [[ "$1" == "realpath" ]]; then
    echo "$realpath"
else
    echo "FAILED: unknown argument $1"
    exit 1
fi
