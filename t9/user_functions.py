import asyncio
import regex as re
import shlex
from collections import deque
from datetime import datetime

from .echo_formatter import EchoFormatter
from .exceptions import *
from .server_exec import ServerExecSession
from .components import InterfaceComponent


class UserFunctions(InterfaceComponent):
    def __init__(self, config, send_line):
        InterfaceComponent.__init__(self, config, send_line)
        self.functions = {}
        self.function_names = []
        self.exec_counter = asyncio.Queue()
        self.db = None

        my_nick_re = config['nick'] + '|' + config['nick'].lower()
        self.function_set_re = re.compile(r'^(?:(' + my_nick_re + r')[:,]? )?([^<]+?) ?<([^>]+)> ?(.*)')

    def __getitem__(self, key):
        return self.functions[key]

    def load_from_db(self, db):
        self.db = db
        self.functions.clear()

        with db.cursor() as dbc:
            dbc.execute('SELECT func_name, parent_func, func_data, setter_nick, set_time FROM funcs')
            for func_name, parent_func, func_data, setter_nick, set_time in dbc:
                self.functions[func_name] = {
                    'func': parent_func,
                    'func_data': func_data,
                    'setter_nick': setter_nick,
                    'set_time': set_time,
                }
            self.update_sorted_names()

    def persist_function_def(self, new_func_name, new_parent_func, new_func_data, nick):
        if self.db:
            self.logger.debug(f'Storing function {new_func_name} in db')
            with self.db.cursor() as dbc:
                dbc.execute('INSERT INTO funcs (func_name, parent_func, func_data, setter_nick) '
                            'VALUES (%(func_name)s, %(parent_func)s, %(func_data)s, %(nick)s) '
                            'ON CONFLICT ON CONSTRAINT funcs_pkey DO UPDATE SET '
                              'parent_func=%(parent_func)s, '
                              'func_data=%(func_data)s, '
                              'setter_nick=%(nick)s, '
                              'set_time=now()',
                            {
                                'func_name': new_func_name,
                                'parent_func': new_parent_func,
                                'func_data': new_func_data,
                                'nick': nick,
                            })
                self.db.commit()
        else:
            self.logger.debug(f'No database configured -- {new_func_name} will not be persisted')

    def try_define_function(self, line):
        define_allowed = not self.config['define_functions_in_t9_channels_only'] or self.is_t9_chan(line.args[0])
        m = self.function_set_re.match(line.text)
        if m and define_allowed and (m.group(1) or self.is_t9_chan(line.args[0])):
            new_func_trigger = m.group(2).strip()
            if not new_func_trigger:
                return
            if new_func_trigger.endswith(' is'):
                new_func_trigger = new_func_trigger[:-3]
            if new_func_trigger.lower() == 'exec':
                self.respond(line)(f'Not setting function {new_func_trigger} - name is reserved')
                return
            new_parent_func = m.group(3).strip()
            new_func_data = m.group(4)
            if not new_parent_func[0] in self.config['primitive_leaders'] and not self.match_function(new_parent_func):
                self.respond(line)('No match for parent function')
                return

            self.logger.debug(f'Starting to store definition for function {new_func_trigger}')
            self.persist_function_def(new_func_trigger,
                                      new_parent_func,
                                      new_func_data,
                                      line.handle.nick)
            new_func_def = {
                'func': new_parent_func,
                'func_data': new_func_data,
                'setter_nick': line.handle.nick,
                'set_time': datetime.now(),
            }
            self.functions[new_func_trigger] = new_func_def
            self.update_sorted_names()
            self.respond(line)(f'Set new function {new_func_trigger}')
            return new_func_def
        else:
            return False

    def update_sorted_names(self):
        self.function_names = list(self.functions.keys())
        self.function_names.sort(key=lambda e: len(e), reverse=True)

    def match_function(self, user_string):
        for func_name in self.function_names:
            if func_name[0] == '!' and user_string[0] in self.config['user_leaders']:
                user_string = '!' + user_string[1:]
            if func_name[-1] == '$':
                if user_string == func_name[:-1]:
                    return func_name, '', None
            elif len(func_name) >= 3 and func_name[0] == '/' and func_name[-1] == '/':
                trigger_re = func_name[1:-1]
                trigger_mo = re.search(trigger_re, user_string)
                if trigger_mo:
                    return func_name, user_string, trigger_mo
            elif func_name[-1] == '?':
                if user_string == func_name:
                    return func_name, '', None
            else:
                func_prefix = func_name + ' '
                if user_string.startswith(func_prefix):
                    return func_name, user_string[len(func_prefix):], None
                elif user_string == func_name:
                    return func_name, '', None
        return False

    async def run_match_function(self, line, user_string):
        m = self.match_function(user_string)
        if m:
            func_name, param, regex_match = m
            self.logger.info(f'Function "{func_name}" triggered by line <= {line}')
            await self.run_function(line, func_name, param, regex_match)
        else:
            self.logger.debug('No matched function')

    async def handle_privmsg(self, line):
        if self.try_define_function(line):
            self.logger.debug('Successfully defined function')
        else:
            await self.run_match_function(line, line.text)

    def delete_function(self, del_input, respond=None):
        if respond is None:
            respond = self.logger.info

        m = self.match_function(del_input)
        if not m:
            respond(f'No function matches "{del_input}"')
            return

        func_key, func_input, match_obj = m

        try:
            del self.functions[func_key]
            self.update_sorted_names()
            self.logger.debug(f'Deleted local function "{func_key}"')
        except KeyError:
            self.logger.error(f'KeyError while deleting function "{func_key}"')
            respond("Well, it shouldn't bother you any more ...")
            return

        if self.db:
            with self.db.cursor() as dbc:
                dbc.execute('DELETE FROM funcs WHERE func_name=%s', (func_key,))
                if dbc.rowcount > 0:
                    self.logger.debug(f'Deleted function from database "{func_key}"')
                else:
                    self.logger.warning(f'"{del_input}" matched function "{func_key}" but no rows deleted from database')
                self.db.commit()

        respond(f'Deleted function "{func_key}"')

    async def run_function(self, line, func_key, func_input='', regex_match=None, stack=None):
        """Run a user-defined function"""
        if stack is None:
            stack = deque()

        stack_limit = self.config['stack_limit']
        if len(stack) > stack_limit:
            self.logger.info(f'Exceeded stack limit of {stack_limit}')
            return
        if func_key[0] in self.config['primitive_leaders']:
            func_data = stack[0][1]
            await self.run_primitive(line, func_key[1:], func_data, func_input, regex_match, stack)
        else:
            func_def = self.functions[func_key]

            if func_def['func'][0] in self.config['primitive_leaders']:
                parent_func_key = func_def['func']
            else:
                m = self.match_function(func_def['func'])
                if not m:
                    self.logger.warning(f'No function matches parent <{func_def["func"]}>')
                    return

                parent_func_key, parent_func_input, parent_match_obj = m
                if parent_func_input:
                    func_input = parent_func_input
                if parent_match_obj:
                    regex_match = parent_match_obj

            stack.appendleft((func_key, func_def['func_data']))

            self.logger.debug(f'Running parent function "{parent_func_key}" for function "{func_key}"')
            await self.run_function(line, parent_func_key, func_input, regex_match, stack)

    async def run_primitive(self, line, cmd, args, func_input, regex_match, stack):
        """This defines the names of built-in primitive functions"""
        if cmd == 'exec':
            await self.exec(line, args, func_input, stack, regex_match=regex_match)
        elif cmd == 'echo':
            self.echo(line, args, func_input, stack, regex_match)
        else:
            raise BuiltinNotFoundError(cmd)

    def echo(self, line, echo_fmt, func_input, stack, regex_match):
        formatter = EchoFormatter(line, func_input, stack, regex_match)
        self.respond(line)(formatter.format(echo_fmt))

    @staticmethod
    def _regex_env_vars(regex_match, env: dict):
        if not regex_match:
            return

        env['T9_MATCH_0'] = regex_match.group(0)
        for i, cap_str in enumerate(regex_match.captures(0)):
            env[f"T9_MATCH_CAPTURE_0_{i}"] = cap_str
        for i, group_str in enumerate(regex_match.groups(default='')):
            env[f"T9_MATCH_{i + 1}"] = group_str
            for j, cap_str in enumerate(regex_match.captures(i)):
                env[f"T9_MATCH_CAPTURE_{i + 1}_{j}"] = cap_str
        for name, group_str in regex_match.groupdict(default='').items():
            env[f"T9_MATCH_{name}"] = group_str
            for i, cap_str in enumerate(regex_match.captures(name)):
                env[f"T9_MATCH_CAPTURE_{name}_{i}"] = cap_str

    @staticmethod
    def _stack_env_vars(stack, env: dict):
        if not stack:
            return
        if len(stack) <= 1:
            return

        for i in range(1, len(stack)):
            stack_func, stack_data = stack[i]
            env[f"T9_STACK_{i}_FUNC"] = stack_func
            env[f"T9_STACK_{i}_DATA"] = stack_data

    def _secrets_env_vars(self, line, called_as, stack, env: dict):
        if not self.db:
            return

        func_setter = None
        try:
            if stack:
                # called in function stack
                func_def = self.functions[called_as]
                func_setter = func_def['setter_nick']
            else:
                # called as command
                if self.is_t9_chan(line.args[0]):
                    func_setter = line.handle.nick
                else:
                    self.logger.debug('exec call from non-t9 chan!')
        except KeyError as e:
            self.logger.debug(f'KeyError looking up function setter for "{called_as}" call: {e.args[0]} - secrets will not be passed this call')

        if not func_setter:
            return

        with self.db.cursor() as dbc:
            dbc.execute("SELECT env_var, secret FROM secrets WHERE owner_nick=%s",
                        (func_setter,))
            for env_var, secret in dbc:
                if self.is_valid_env_var(env_var):
                    env[env_var] = secret
                    self.logger.debug(f'Injecting secret ${env_var} for {func_setter}')
                else:
                    self.logger.debug('Invalid env_var name stored in database!')

    def _user_db_env_vars(self, env: dict):
        if not self.config['user_db']:
            return
        dsn = []
        have_manual_dsn = False
        for config_key, config_val in self.config['user_db'].items():
            env_suffix = config_key.upper()
            dsn_key = config_key.lower()
            env[f'T9_DB_{env_suffix}'] = str(config_val)
            if dsn_key == 'dsn':
                have_manual_dsn = True
            else:
                dsn.append(f'{dsn_key}={config_val}')
        if not have_manual_dsn:
            dsn = ' '.join(dsn)
            env['T9_DB_DSN'] = dsn

    async def exec(self, line, func_data, func_input='', stack=None, timelimit=None, regex_match=None):
        """The main thing T9 does - exec user input on a container"""
        if timelimit is None:
            timelimit = self.config['function_exec_time']

        cmd_args = shlex.split(func_data)

        while cmd_args[0][0] == '-':
            self.logger.debug('Removing leading - from command')
            cmd_args[0] = cmd_args[0][1:]

        proto_args_str = ' '.join(line.args)
        if line.cmd == 'PRIVMSG':
            line_channel = line.args[0]
        else:
            line_channel = ''

        exec_locale = self.config['exec_locale']
        if stack:
            called_as = stack[0][0]
        else:
            called_as = ''

        env = {
            'LC_ALL': exec_locale,
            'LANG': exec_locale,
            'T9_FUNC': called_as,
            'T9_INPUT': func_input,
            'T9_NICK': line.handle.nick,
            'T9_USER': line.handle.user,
            'T9_VHOST': line.handle.host,
            'T9_CHANNEL': line_channel,
            'T9_PROTO_LINE': str(line),
            'T9_PROTO_COMMAND': line.cmd,
            'T9_PROTO_ARGS': proto_args_str,
        }

        if self.config['exec_python_utf8']:
            env['PYTHONUTF8'] = '1'
            env['PYTHONIOENCODING'] = 'utf-8:replace'

        self._regex_env_vars(regex_match, env)
        self._stack_env_vars(stack, env)
        self._secrets_env_vars(line, called_as, stack, env)
        self._user_db_env_vars(env)

        self.logger.info(f'Running $exec [{func_data}]')

        # effectively increment the counter
        self.exec_counter.put_nowait(None)

        # try-finally block to guarantee we decrement the above once done
        try:
            if timelimit > 90:
                self.respond(line)(f'Running for up to {timelimit} seconds')

            async with ServerExecSession(self.config) as server:
                try:
                    status, stdout, stderr = await server.exec(
                        args=cmd_args,
                        env=env,
                        user='user:user',
                        cwd='/home/user',
                        timeout=timelimit,
                    )

                    try:
                        out_line = stdout.decode('utf-8').splitlines()[0].rstrip()
                        if out_line:
                            self.respond(line)(out_line)
                        else:
                            self.logger.debug('Stdout line is empty')
                    except IndexError:
                        self.logger.debug('No stdout lines')

                    stderr = stderr.decode('utf-8').strip()
                    if stderr:
                        err_short_url = self.pastebin(stderr)
                        if err_short_url:
                            self.user_log(line)(f'$exec [{func_data}] STDERR output at {err_short_url}')
                        else:
                            err_line = stderr.splitlines()[-1].strip()
                            self.user_log(line)(f'$exec [{func_data}] STDERR final line | {err_line}')
                    else:
                        self.logger.debug('No stderr output')

                    self.user_log(line)(f'$exec [{func_data}] exited {status}')

                except asyncio.TimeoutError:
                    self.user_log(line)(f'$exec [{func_data}] timed out')
        finally:
            # effectively decrement the counter
            self.exec_counter.get_nowait()
            self.exec_counter.task_done()
