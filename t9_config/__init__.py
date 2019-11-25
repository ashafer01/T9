import logging.config
import os
import sys
import yaml

logger = logging.getLogger('t9_config')
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

SPEC_CONFIG_LOCATIONS = (
    'config.yaml', 'config.yml',
    '~/.config/t9.yaml', '~/.config/t9.yml',
    '/etc/t9/config.yaml', '/etc/t9/config.yml',
)


def _real_path(fn):
    fn = os.path.expanduser(fn)
    fn = os.path.expandvars(fn)
    return os.path.abspath(fn)


def _cli_arg():
    try:
        return sys.argv[1]
    except IndexError:
        pass


def _env_var():
    try:
        return os.environ['T9_CONFIG_FILE']
    except KeyError:
        pass


def _spec_location():
    for fn in SPEC_CONFIG_LOCATIONS:
        try:
            rfn = _real_path(fn)
            if os.path.exists(rfn):
                return fn
        except Exception as e:
            logger.error(f'Error while checking config spec location {fn}: {e}')


_name_fetchers = (
    (_cli_arg, 'Using config file from $1'),
    (_env_var, 'Using config file from $T9_CONFIG_FILE'),
    (_spec_location, 'Using spec config file location'),
)


def _fetch_config_filename():
    for fetch, message in _name_fetchers:
        config_fn = fetch()
        if config_fn:
            logger.info(f'{message} = "{config_fn}"')
            return _real_path(config_fn)

    spec_list = ', '.join([l for l in SPEC_CONFIG_LOCATIONS if not l.endswith('.yml')])
    logger.error('FATAL: Unable to locate config filename, please pass as '
                 f'$1, $T9_CONFIG_FILE, or use a spec location: {spec_list}')
    sys.exit(1)


def _read_config_file(config_fn):
    with open(config_fn) as f:
        return yaml.safe_load(f.read())


_env_map = (
    ('T9_CONFIG_HOST', 'host'),
    ('T9_CONFIG_PORT', 'port'),
    ('T9_CONFIG_NICK', 'nick'),
    ('T9_CONFIG_USER', 'user'),
    ('T9_CONFIG_VHOST', 'vhost'),
    ('T9_CONFIG_REALNAME', 'realname'),
    ('T9_CONFIG_PASSWORD', 'password'),
    ('T9_CONFIG_EXEC_SERVER_BASE_URL', 'exec_server_base_url'),
    ('T9_CONFIG_CONSOLE_CHANNEL', 'console_channel'),
    ('T9_CONFIG_CONSOLE_CHANNEL_LEVEL', 'console_channel_level'),
    ('T9_CONFIG_HELP', 'help'),
    ('T9_CONFIG_PRIMITIVE_LEADERS', 'primitive_leaders'),
    ('T9_CONFIG_COMMAND_LEADERS', 'command_leaders'),
    ('T9_CONFIG_USER_LEADERS', 'user_leaders'),
    ('T9_CONFIG_PASTEBIN_FUNCTION', 'pastebin_function'),
    ('T9_CONFIG_DCC_MAX_SIZE', 'dcc_max_size'),
    ('T9_CONFIG_DCC_DIR', 'dcc_dir'),
    ('T9_CONFIG_SECURE_BASE', 'secure_base'),
    ('T9_CONFIG_REL_SECURE_BASE', 'rel_secure_base'),
    ('T9_CONFIG_FUNCTION_EXEC_TIME', 'function_exec_time'),
    ('T9_CONFIG_DEFAULT_EXEC_TIME', 'default_exec_time'),
    ('T9_CONFIG_MAX_EXEC_TIME', 'max_exec_time'),
    ('T9_CONFIG_EXEC_LOCALE', 'exec_locale'),
    ('T9_CONFIG_STACK_LIMIT', 'stack_limit'),
)


def _basic_env_config(_config):
    for env_var, config_key in _env_map:
        try:
            env_val = os.environ[env_var]
            _config[config_key] = env_val
        except KeyError:
            pass


_env_map_bools = (
    ('T9_CONFIG_DEFINE_FUNCTIONS_IN_T9_CHANNELS_ONLY', 'define_functions_in_t9_channels_only'),
    ('T9_CONFIG_EXEC_PYTHON_UTF8', 'exec_python_utf8'),
)


def _bool_env_config(_config):
    for env_var, config_key in _env_map_bools:
        try:
            env_val = os.environ[env_var].lower()
            if env_val == 'true':
                _config[config_key] = True
            elif env_val == 'false':
                _config[config_key] = False
            else:
                raise RuntimeError(f'Invalid boolean string for {env_var}, must be "true" or "false", got "{env_val}"')
        except KeyError:
            pass


def _csl(val):
    return [i.strip() for i in val.split(',')]


_env_map_lists = (
    ('T9_CONFIG_CHANNELS', 'channels'),
    ('T9_CONFIG_IGNORE', 'ignore'),
)


def _list_env_config(_config):
    for env_var, config_key in _env_map_lists:
        try:
            channels_value = os.environ[env_var]
            _config[config_key] = _csl(channels_value)
        except KeyError:
            pass


_db_env_prefix_config_key_map = (
    ('T9_CONFIG_DB_', 'db'),
    ('T9_CONFIG_USER_DB_', 'user_db'),
)

_db_suffix_env_map = {
    'NAME': 'dbname',
    'DBNAME': 'dbname',
}


def _db_env_config(_config):
    for var_name in os.environ:
        for prefix, config_key in _db_env_prefix_config_key_map:
            if var_name.startswith(prefix):
                prefix_len = len(prefix)
                suffix = var_name[prefix_len:]
                if not suffix:
                    raise RuntimeError(f'Missing suffix on environment variable {var_name}')
                config_subkey = _db_suffix_env_map.get(suffix, suffix.lower())
                db_config = _config.setdefault(config_key, {})
                db_config[config_subkey] = os.environ[var_name]


def _invite_allowed_env_config(_config):
    try:
        invite_value = os.environ['T9_CONFIG_INVITE_ALLOWED'].lower()
        if invite_value == 'true':
            config_value = True
        elif invite_value == 'false':
            config_value = False
        else:
            config_value = _csl(invite_value)
        _config['invite_allowed'] = config_value
    except KeyError:
        pass


def _env_config(_config):
    _basic_env_config(_config)
    _bool_env_config(_config)
    _list_env_config(_config)
    _db_env_config(_config)
    _invite_allowed_env_config(_config)


def _load_config():
    config_fn = _fetch_config_filename()
    _config = _read_config_file(config_fn)
    _env_config(_config)
    return _config


config = _load_config()
logging.config.dictConfig(config.get('logging', {'version': 1}))

__all__ = ['config', 'SPEC_CONFIG_LOCATIONS']
