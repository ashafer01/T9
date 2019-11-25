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

Documentation is available in the [GitHub wiki](https://github.com/ashafer01/T9/wiki).

Originally built on Python 3.7.3

## Quickstart

Use `./quickstart.sh` to build images and bring up services in the foreground for testing and demos. This includes
a local IRC server and Postgres database. Making direct use of the [quickstart orchestration](orchestration/quickstart)
is also a good starting point if you *don't* have an existing IRC server or DB.

Point your IRC client at `localhost:42667` and join `#T9-playground` to try it out.

## Standalone

Using or modifying the [standalone orchestration](orchestration/standalone) is recommended for most users who wish to
use T9 with an existing IRC server and database.

## Custom and Manual Deployments

T9 does not explicitly require the use of Docker as of 0.2.0. The exec server and T9 are both normal Python
applications. For any semblance of security, running the exec server in some kind of isolated environment is strongly
recommended. This environment could be a Docker container, virtual machine, Raspberry Pi, or anything in between.

Starting from a freshly cloned git repo, to install and run the exec server:

```bash
python3 setup.t9-exec-server.py install
python3 -m t9_exec_server
```

And for T9 itself:

```bash
python3 setup.t9-irc-bot.py install

# Assuming a valid config.yaml is in the current directory
python3 -m t9

# You can also pass in the path to a config file
python3 -m t9 ~/some/dir/t9.yaml

# Finally you can pass in a config filename by environment variable
export T9_CONFIG_FILE="/opt/my_deployments/t9/config.yaml"
python3 -m t9
```

