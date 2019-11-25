import logging
import re
from importlib import import_module

env_var_name_re = re.compile('^[a-zA-Z][a-zA-Z0-9_]{3,31}$')


def parse_timelimit(time_arg):
    try:
        return int(time_arg)
    except ValueError:
        pass
    if time_arg.endswith('s'):
        timelimit = int(time_arg[:-1])
    elif time_arg.endswith('m'):
        timelimit = int(time_arg[:-1]) * 60
    elif time_arg.endswith('h'):
        timelimit = int(time_arg[:-1]) * 3600
    else:
        raise ValueError('Unknown time units')
    return timelimit


class Component(object):
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(config['nick'])


class InterfaceComponent(Component):
    def __init__(self, config, send_line):
        Component.__init__(self, config)
        self.send_line = send_line

        self._t9_channel_prefix = '#' + config['nick'].lower() + '-'

        cfg_pastebin_func = config.get('pastebin_function')
        if cfg_pastebin_func:
            mod_name, obj_name = cfg_pastebin_func.rsplit('.', 1)
            mod = import_module(mod_name)
            obj = getattr(mod, obj_name)
            self._pastebin_func = obj
        else:
            self._pastebin_func = None

    def pastebin(self, text):
        if self._pastebin_func:
            return self._pastebin_func(text)
        else:
            return False

    def t9_chan(self, channel):
        return channel.lower().startswith(self._t9_channel_prefix)

    def user_log(self, line):
        line_chan = line.args[0].lower()
        if line_chan.startswith('#'):
            if self.t9_chan(line_chan) and line_chan != self.config['console_channel']:
                def user_log(msg):
                    self.send_line(f'PRIVMSG {line_chan} :{msg}')
            else:
                user_log = self.logger.info
        else:
            def user_log(msg):
                self.send_line(f'PRIVMSG {line.handle.nick} :{msg}')
        return user_log

    def respond(self, line):
        line_chan = line.args[0].lower()
        if line_chan == self.config['console_channel']:
            respond = self.logger.info
        elif line_chan.startswith('#'):
            def respond(msg):
                self.send_line(f'PRIVMSG {line_chan} :{msg}')
        else:
            def respond(msg):
                self.send_line(f'PRIVMSG {line.handle.nick} :{msg}')
        return respond
