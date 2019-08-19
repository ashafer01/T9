import asyncio
import re
import shlex
from collections import deque
from datetime import datetime

from .exceptions import *
from .utils import InterfaceComponent, env_var_name_re


class UserFunctions(InterfaceComponent):
    def __init__(self, config, logger, send_line):
        InterfaceComponent.__init__(self, config, logger, send_line)
        self.functions = {}
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

    def persist_function_def(self, new_func_name, new_parent_func, new_func_data, nick):
        if self.db:
            with self.db.cursor() as dbc:
                dbc.execute('UPDATE funcs SET '
                              'parent_func=%s, '
                              'func_data=%s, '
                              'setter_nick=%s, '
                              'set_time=now() '
                            'WHERE func_name=%s', (
                              new_parent_func,
                              new_func_data,
                              nick,
                              new_func_name,
                            ))
                if dbc.rowcount == 0:
                    dbc.execute('INSERT INTO funcs ('
                                  'func_name, '
                                  'parent_func, '
                                  'func_data, '
                                  'setter_nick ) VALUES '
                                '(%s, %s, %s, %s)', (
                                  new_func_name,
                                  new_parent_func,
                                  new_func_data,
                                  nick,
                                ))
                self.db.commit()

    def try_define_function(self, line):
        define_allowed = not self.config.get('define_functions_in_t9_channels_only') or self.t9_chan(line.args[0])
        m = self.function_set_re.match(line.text)
        if m and define_allowed and (m.group(1) or self.t9_chan(line.args[0])):
            new_func_name = m.group(2).strip()
            if not new_func_name:
                return
            if new_func_name.endswith(' is'):
                new_func_name = new_func_name[:-3]
            if new_func_name.lower() == 'exec':
                self.logger.info(f'Not setting function {new_func_name} - name is reserved')
                return
            self.logger.info(f'Setting new function {new_func_name}')
            new_parent_func = m.group(3).strip()
            new_func_data = m.group(4)
            self.persist_function_def(new_func_name,
                                      new_parent_func,
                                      new_func_data,
                                      line.handle.nick)
            new_func_def = {
                'func': new_parent_func,
                'func_data': new_func_data,
                'setter_nick': line.handle.nick,
                'set_time': datetime.now(),
            }
            self.functions[new_func_name] = new_func_def
            return new_func_def
        else:
            return False

    def match_function(self, user_string):
        func_names = list(self.functions.keys())
        func_names.sort(key=lambda e: len(e), reverse=True)
        run_func = False
        for func_name in func_names:
            run_func = False
            if func_name[0] == '!' and user_string[0] in self.config['user_leaders']:
                user_string = '!' + user_string[1:]
            if func_name[-1] == '$':
                if user_string == func_name[:-1]:
                    return func_name, ''
            elif len(func_name) >= 3 and func_name[0] == '/' and func_name[-1] == '/':
                trigger_re = func_name[1:-1]
                trigger_mo = re.search(trigger_re, user_string)
                if trigger_mo:
                    line.trigger_match = trigger_mo
                    return func_name, user_string
            elif func_name[-1] == '?':
                if user_string == func_name:
                    return func_name, ''
            elif user_string[-1] == '?':
                if user_string[:-1] == func_name:
                    return func_name, ''
            else:
                func_prefix = func_name + ' '
                if user_string.startswith(func_prefix):
                    return func_name, user_string[len(func_prefix):]
                elif user_string == func_name:
                    return func_name, ''
        return False

    async def run_match_function(self, line, user_string):
        m = self.match_function(user_string)
        if m:
            func_name, param = m
            self.logger.info(f'Function {func_name} triggered by line <= {line}')
            await self.run_function(line, func_name, param)
        else:
            self.logger.debug('No matched function')

    async def handle_line(self, line):
        if self.try_define_function(line):
            self.logger.debug('Successfully defined function')
        else:
            await self.run_match_function(line, line.text)

    def delete_function(self, func_name, respond=None):
        if respond is None:
            respond = self.logger.info
        if self.db:
            with self.db.cursor() as dbc:
                dbc.execute('DELETE FROM funcs WHERE func_name=%s', (func_name,))
                if dbc.rowcount > 0:
                    respond(f'Deleted function "{func_name}"')
                    del self.functions[func_name]
                else:
                    respond(f'No function found with name "{func_name}"')
                self.db.commit()
        else:
            self.logger.debug('No database for $rm')
            del self.functions[func_name]
            respond(f'Deleted function "{func_name}"')

    async def run_function(self, line, func_name, func_input='', stack=None):
        """Run a user-defined function"""
        if stack is None:
            stack = deque()

        stack_limit = self.config.get('stack_limit', 4)
        if len(stack) > stack_limit:
            self.logger.info(f'Exceeded stack limit of {stack_limit}')
            return
        if func_name[0] in self.config['primitive_leaders']:
            func_data = stack[0][1]
            await self.run_primitive(line, func_name[1:], func_data, func_input, stack)
        else:
            func_def = self.functions[func_name]
            parent_func_name = func_def['func']
            parent_func_data = func_def['func_data']
            stack.appendleft((func_name, parent_func_data))
            await self.run_function(line, parent_func_name, func_input, stack)

    async def run_primitive(self, line, cmd, args, func_input, stack):
        """This defines the names of built-in primitive functions"""
        if cmd == 'exec':
            await self.exec(line, args, func_input, stack)
        elif cmd == 'echo':
            self.respond(line)(args.rstrip())
        else:
            raise BuiltinNotFoundError(cmd)

    async def exec(self, line, func_data, param='', stack=None, timelimit=None):
        """The main thing T9 does - exec user input on a container"""
        if timelimit is None:
            timelimit = self.config['function_exec_time']

        extra_env = []

        if stack:
            called_as = stack[0][0]

            if len(stack) > 1:
                for i in range(1, len(stack)):
                    stack_func, stack_data = stack[i]
                    extra_env.extend(['-e', f"T9_STACK_{i}_FUNC={stack_func}",
                                      '-e', f"T9_STACK_{i}_DATA={stack_data}"])
        else:
            called_as = ''

        if line.trigger_match:
            extra_env.extend(['-e', f"T9_MATCH_0={line.trigger_match.group(0)}"])
            for i, group_str in enumerate(line.trigger_match.groups(default='')):
                extra_env.extend(['-e', f"T9_MATCH_{i+1}={group_str}"])
            for name, group_str in line.trigger_match.groupdict(default='').items():
                extra_env.extend(['-e', f"T9_MATCH_{name}={group_str}"])

        if self.config['exec_python_utf8']:
            extra_env.extend(['-e', 'PYTHONUTF8=1',
                              '-e', 'PYTHONIOENCODING=utf-8:replace'])

        if self.db:
            func_setter = None
            try:
                if stack:
                    # called in function stack
                    func_def = self.functions[called_as]
                    func_setter = func_def['setter_nick']
                else:
                    # called as command
                    if self.t9_chan(line.args[0]):
                        func_setter = line.handle.nick
                    else:
                        self.logger.debug('exec call from non-t9 chan!')
            except KeyError as e:
                self.logger.debug(f'KeyError looking up function setter for "{called_as}" call: {e.args[0]} - secrets will not be passed this call')

            if func_setter:
                with self.db.cursor() as dbc:
                    dbc.execute("SELECT env_var, secret FROM secrets WHERE owner_nick=%s",
                                (func_setter,))
                    for env_var, secret in dbc:
                        if env_var_name_re.match(env_var) and not env_var.upper().startswith('T9_'):
                            extra_env.extend(['-e', f"{env_var}={secret}"])
                            self.logger.debug(f'Injecting secret ${env_var} for {func_setter}')
                        else:
                            self.logger.debug('Invalid env_var name stored in database!')

        if 'user_db' in self.config:
            extra_env.extend([
                '-e', f"T9_DB_USER={self.config['user_db']['user']}",
                '-e', f"T9_DB_HOST={self.config['user_db']['host']}",
                '-e', f"T9_DB_PORT={self.config['user_db']['port']}",
                '-e', f"T9_DB_NAME={self.config['user_db']['dbname']}",
                '-e', f"T9_DB_DSN=user={self.config['user_db']['user']}"
                               f" host={self.config['user_db']['host']}"
                               f" port={self.config['user_db']['port']}"
                               f" dbname={self.config['user_db']['dbname']}",
            ])

        cmd_args = shlex.split(func_data)
        while cmd_args[0][0] == '-':
            self.logger.debug('Removing leading - from command')
            cmd_args[0] = cmd_args[0][1:]
        self.logger.info(f'Running $exec [{func_data}]')

        proto_args_str = ' '.join(line.args)
        if line.cmd == 'PRIVMSG':
            line_channel = line.args[0]
        else:
            line_channel = ''

        exec_locale = self.config['exec_locale']

        # effectively increment the counter
        self.exec_counter.put_nowait(None)

        # try-finally block to guarantee we decrement the above once done
        try:
            proc = await asyncio.create_subprocess_exec(
                'docker', 'exec', '-i', '-u', 'user:user', '-w', '/home/user',
                '-e', f"LC_ALL={exec_locale}",
                '-e', f"LANG={exec_locale}",
                '-e', f"T9_FUNC={called_as}",
                '-e', f"T9_INPUT={param}",
                '-e', f"T9_NICK={line.handle.nick}",
                '-e', f"T9_USER={line.handle.user}",
                '-e', f"T9_VHOST={line.handle.host}",
                '-e', f"T9_CHANNEL={line_channel}",
                '-e', f"T9_PROTO_LINE={line}",
                '-e', f"T9_PROTO_COMMAND={line.cmd}",
                '-e', f"T9_PROTO_ARGS={proto_args_str}",
                *extra_env,
                self.config['container_name'],
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=2048,
            )

            if timelimit > 90:
                self.respond(line)(f'Running for up to {timelimit} seconds')

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
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

                self.user_log(line)(f'$exec [{func_data}] exited {proc.returncode}')

            except asyncio.TimeoutError:
                self.user_log(line)(f'$exec [{func_data}] timed out')
        finally:
            # effectively decrement the counter
            self.exec_counter.get_nowait()
            self.exec_counter.task_done()
