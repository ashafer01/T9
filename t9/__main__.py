import asyncio
import logging.config
import os
import sys
import yaml

from .bot import bot

SPEC_CONFIG_LOCATIONS = ('config.yaml', 'config.yml')

try:
    config_fn = sys.argv[1]
    sys.stderr.write(f'Using config file from $1 = "{config_fn}"\n')
except IndexError:
    config_fn = None

if not config_fn:
    try:
        config_fn = os.environ['T9_CONFIG_FILE']
        sys.stderr.write(f'Using config file from $T9_CONFIG_FILE = "{config_fn}"\n')
    except KeyError:
        pass

if not config_fn:
    for fn in SPEC_CONFIG_LOCATIONS:
        if os.path.exists(fn):
            config_fn = fn
            sys.stderr.write(f'Using spec config file location = "{config_fn}"\n')
            break

if not config_fn:
    spec_list = ', '.join(SPEC_CONFIG_LOCATIONS)
    sys.stderr.write(f'Unable to locate config filename, please pass as $1, $T9_CONFIG_FILE, or use a spec location: {spec_list}\n')
    sys.exit(1)

with open(config_fn) as f:
    config = yaml.safe_load(f.read())

logging.config.dictConfig(config.get('logging', {'version': 1}))

asyncio.run(bot(config), debug=True)
