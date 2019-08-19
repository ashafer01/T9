# T9 "Anything" IRC Bot

T9 allows users to define their own functions.

They can have a completely arbitrary trigger based on an input line in a
channel.

They can, very boringly, echo back a single string.

Much more interestingly, they can exec an arbitrary command on a Docker
container, with a system of environment variables passed in allowing complex
interactions with the IRC protocol, the state of the bot, and external
resources.

This is not for every IRC server. Effort has been made to try to keep things
reasonably secure, but it is by no means perfect. As the code sits now it is
almost trivial to get a root shell on the container, and then of course
the security of the system reduces to docker security, which is bemoaned by
many.

The security is also closely linked to IRC security. If you have a few trusted
users on a larger IRC server it is reasonable to allow only those users to have
a potential for exploiting T9 (unless of course a function itself has
exploits).

Check the example config for more information.

To install from source:

```
python3 setup.py install
```

To start, assuming a complete config file is in the working directory:

```
python3 -m t9
```

You can also pass a config file location:

```
python3 -m t9 ~/some/dir/t9.yaml
```

Finally you can set the `T9_CONFIG_FILE` environment variable to the path to
a config file.
