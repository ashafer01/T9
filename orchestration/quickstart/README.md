# quickstart Orchestration

This orchestration is meant for testing or demos on your local machine. It can also be used as a basis for
modification if you need to set up a new database and/or IRC server (since this orchestration will create both by
default).

The `quickstart.sh` script in the root of this repo will take care of
setting this up from scratch, including a simple configuration and
loading the initial database schema.

Only use the script for initial setup. If you want to re-run it again,
just use `docker-compose up` from this directory as normal.

Once docker-compose is running, point your IRC client at `localhost:42667` and join `#T9-console`. Check the
[user docs](https://github.com/ashafer01/T9/wiki/T9-User-Docs) to learn how to define your first function. You can
then join `#general` to interact with T9 without seeing log messages.