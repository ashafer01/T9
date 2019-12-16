from dataschema import Type, TypeSpec, IterSpec, DictSpec, Reference
from .utils import parse_time_interval

lowercase_string_list = IterSpec(Type(str, lambda s: s.lower()))
optional_lowercase_string_list = lowercase_string_list.copy(optional=True, default=list)
optional_string = TypeSpec((str, None))
optional_bool_default_true = TypeSpec((bool, None), default=True)

internal_leaders = optional_string.copy(default='$')

db_schema = DictSpec({str: (str, int)}, optional=True)

exec_time_schema = TypeSpec(
    types=(int, float, Type(str, parse_time_interval), None),
    constraints=(lambda limit: limit >= 1, 'Time limit must be >= 1 second'),
    default='10s',
)

extra_handshake_schema = TypeSpec(
    types=(
        IterSpec(str),
        Type(str, lambda s: [s]),
        False,
        None,
    ),
    constraints=(
        lambda l: all([1 < len(s) <= 380 for s in l]),
        'Extra handshake lines must be 1-380 characters'
    ),
    is_unset=lambda v: not v,
    default=list
)

config_schema = DictSpec(
    schema={
        "host": str,
        "port": TypeSpec(
            types=(int, Type(str, lambda s: int(s)), None),
            constraints=(lambda port: 1 <= port <= 65535, 'Out of port range'),
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
        "console_channel": TypeSpec((Type(str, lambda s: s.lower()), None)),
        "console_channel_level": TypeSpec(
            types=(str, False, None),
            default='INFO',
        ),
        "channels": optional_lowercase_string_list,
        "passive_join": optional_bool_default_true,
        "primitive_leaders": internal_leaders,
        "command_leaders": internal_leaders,
        "user_leaders": optional_string.copy(default='!.;'),
        "channel_leaders": optional_string.copy(default='#&'),
        "dcc_max_size": TypeSpec(
            types=(int, None),
            constraints=(lambda v: v > 512, 'Must be larger than IRC message'),
        ),
        "dcc_dir": optional_string,
        "secure_base": optional_string,
        "db": db_schema,
        "user_db": db_schema,
        "ignore": optional_lowercase_string_list,
        "invite_allowed": TypeSpec(
            types=(lowercase_string_list, False, None),
            default=list,
        ),
        "define_functions_in_t9_channels_only": TypeSpec(
            types=(bool, None),
            default=True
        ),
        "function_exec_time": exec_time_schema,
        "default_exec_time": exec_time_schema,
        "max_exec_time": exec_time_schema,
        "exec_locale": TypeSpec(
            types=(str, None),
            default='C',
        ),
        "exec_python_utf8": TypeSpec(
            types=(bool, None),
            default=True,
        ),
        "stack_limit": TypeSpec(
            types=(int, None),
            default=4,
        ),
        "logging": TypeSpec(
            types=(dict, None),
            default=lambda: {'version': 1},
        ),
        "pastebin_function": optional_string,
    },
    references=(
        ("console_channel", Reference(
            update=(lambda cfg, console_channel: not console_channel,
                    lambda cfg, _: '#{nick}-console'.format(**cfg).lower()),
            test=(lambda cfg, console_channel: console_channel.lower().startswith('#{nick}-'.format(**cfg).lower()),
                  'Console channel must begin with configured nickname'),
        )),
        ("channels", Reference(
            update=(lambda cfg, channels: cfg['console_channel'] not in channels,
                    lambda cfg, channels: [*channels, cfg['console_channel']]),
        )),
        ("logging", Reference(
            test=(lambda cfg, logging: cfg['nick'] in logging['loggers'] if 'loggers' in logging else True,
                  'Loggers have been configured but no logger corresponding to the configured nickname is defined'),
        )),
    ),
)
