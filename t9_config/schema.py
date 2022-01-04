import sys
sys.path.insert(0, '/Users/alex/git/dataschema')
from dataschema import Type, TypeSpec, IterSpec, DictSpec, Test, Update
from .utils import parse_time_interval

lowercase_string_list = IterSpec(Type(str, lambda s: s.lower()))
optional_lowercase_string_list = lowercase_string_list(optional=True, default=list)
optional_string = TypeSpec(str, optional=True)
optional_bool_default_true = TypeSpec(bool, optional=True, default=True)
optional_bool_default_false = TypeSpec(bool, optional=True, default=False)

internal_leaders = optional_string(default='$')

db_schema = DictSpec({str: (str, int)}, optional=True)

exec_time_schema = TypeSpec(
    types=(int, float, Type(str, parse_time_interval)),
    constraints=(lambda limit: limit >= 1,
                 'Time limit must be >= 1 second'),
    optional=True,
    default='10s',
)

extra_handshake_schema = TypeSpec(
    types=(
        IterSpec(str),
        Type(str, lambda s: [s]),
        False,
    ),
    constraints=(
        lambda l: all([1 < len(s) <= 380 for s in l]),
        'Extra handshake lines must be 1-380 characters'
    ),
    is_unset=lambda v: not v,
    optional=True,
    default=list,
)

config_schema = DictSpec(
    schema={
        "host": str,
        "port": TypeSpec(
            types=(int, Type(str, int)),
            constraints=(lambda port: 1 <= port <= 65535, 'Out of port range'),
            optional=True,
            default=6667,
        ),
        "tls": bool,
        "tls_verify": optional_bool_default_true,
        "tls_ca_file": optional_string,
        "tls_ca_directory": optional_string,
        "tls_client_cert": optional_string,
        "tls_client_private_key": optional_string,
        "password": optional_string,
        "extra_handshake": extra_handshake_schema,
        "nick": str,
        "user": str,
        "vhost": str,
        "realname": str,
        "exec_server_base_url": str,
        "help": str,
        "console_channel": TypeSpec(
            types=Type(str, lambda s: s.lower()),
            optional=True,
        ),
        "console_channel_level": TypeSpec(
            types=(str, False),
            optional=True,
            default='INFO',
        ),
        "channels": optional_lowercase_string_list,
        "passive_join": optional_bool_default_true,
        "primitive_leaders": internal_leaders,
        "command_leaders": internal_leaders,
        "user_leaders": optional_string(default='!.;'),
        "channel_leaders": optional_string(default='#&'),
        "dcc_max_size": TypeSpec(
            types=int,
            optional=True,
            default=(10 * 1024**2),  # 10MB
            constraints=(lambda v: v > 512,
                         'Must be larger than IRC message'),
        ),
        "dcc_dir": optional_string,
        "secure_base": optional_string,
        "db": db_schema,
        "user_db": db_schema,
        "ignore": optional_lowercase_string_list,
        "invite_allowed": TypeSpec(
            types=(lowercase_string_list, False),
            optional=True,
            default=list,
        ),
        "define_functions_in_t9_channels_only": optional_bool_default_false,
        "function_exec_time": exec_time_schema,
        "default_exec_time": exec_time_schema,
        "max_exec_time": exec_time_schema,
        "exec_locale": optional_string(default='C'),
        "exec_python_utf8": optional_bool_default_true,
        "stack_limit": TypeSpec(
            types=int,
            optional=True,
            default=4,
        ),
        "logging": TypeSpec(
            types=dict,
            optional=True,
            default=lambda: {'version': 1},
            constraints=(lambda v: 'version' in v,
                         'logging version key is required'),
        ),
        "pastebin_function": optional_string,
    },
    post=(
        Update('console_channel', 'nick',
               gate=lambda console_channel, _: not console_channel,
               update=lambda _, nick: f'#{nick.lower()}-console'),
        Test('console_channel', 'nick',
             test=lambda console_channel, nick: console_channel.startswith(f'#{nick.lower()}-'),
             message='console_channel must begin with configured nick'),
        Update('channels', 'console_channel',
               gate=lambda channels, console_channel: console_channel not in channels,
               update=lambda channels, console_channel: [*channels, console_channel]),
        Test('logging', 'nick',
             test=lambda logging, nick: 'loggers' not in logging or nick in logging['loggers'],
             message='Loggers have been configured but no logger corresponding to the configured nickname is defined')
    ),
)
