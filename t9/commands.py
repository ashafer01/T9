import asyncio
import shlex

from .utils import parse_timelimit, InterfaceComponent, env_var_name_re


class ExclusiveContainerControl(object):
    def __init__(self, logger, sync_lock, exec_counter):
        self.sync_lock = sync_lock
        self.exec_counter = exec_counter
        self.logger = logger

    async def __aenter__(self):
        await self.sync_lock.acquire()
        await self.exec_counter.join()
        self.logger.debug('Exclusive container control acquired')
        return

    async def __aexit__(self, etype, e, trace):
        self.sync_lock.release()
        self.logger.debug('Exclusive container control released')


class Commands(InterfaceComponent):
    def __init__(self, config, logger, db, functions, sync_lock, send_line):
        InterfaceComponent.__init__(self, config, logger, send_line)
        self.db = db
        self.functions = functions
        self.exclusive_container_control = ExclusiveContainerControl(logger, sync_lock, functions.exec_counter)

    def channel_command_candidate(self, line):
        return line.args[0][0] == '#' and line.text[0] in self.config['command_leaders']

    def pm_command_candidate(self, line):
        return line.args[0][0] != '#' and line.text[0] in self.config['command_leaders']

    def _find_cmd_func(self, func_prefix, cmd):
        cmd_func = None
        for cmd_suffix in (cmd.lower(), cmd.lower().replace('-', '_')):
            try:
                return getattr(self, func_prefix + cmd_suffix)
            except AttributeError:
                pass

    async def _find_run_cmd(self, func_prefix, line, cmd, args):
        cmd_func = self._find_cmd_func(func_prefix, cmd)
        if cmd_func:
            self.logger.info(f'Command ${cmd} triggered by line <= {line}')
            await cmd_func(line, cmd, args)
            return True

    async def handle_line(self, line):
        """Run a built-in command"""

        if line.text[0] not in self.config['command_leaders']:
            self.logger.debug('Missing command leader')
            return

        try:
            cmd, args = line.text[1:].split(' ', 1)
        except ValueError:
            cmd = line.text[1:]
            args = ''

        # Channel commands
        if line.args[0].startswith('#'):
            # Try public command
            if await self._find_run_cmd('public_cmd_', line, cmd, args):
                return

            # gate t9 console/playground channel
            if not self.t9_chan(line.args[0]):
                self.logger.warn('Ignoring possible command in non-playground channel')
                return

            # try t9 channel command
            if await self._find_run_cmd('cmd_', line, cmd, args):
                return

            self.user_log(line)(f'Unknown command {cmd}')

        # PM Commands
        else:
            if await self._find_run_cmd('pm_cmd_', line, cmd, args):
                return

            self.user_log(line)(f'Unknown PM command {cmd} - most commands only available in t9 channels')

    async def public_cmd_help(self, line, cmd, args):
        self.respond(line)(self.config['help'])

    async def public_cmd_rm(self, line, cmd, args):
        self.functions.delete_function(args, self.respond(line))

    async def cmd_exec(self, line, cmd, args):
        """Command form of $exec"""
        arg_words = args.split(' ')
        if arg_words[0] == '-t':
            try:
                time_arg = arg_words[1]
            except IndexError:
                self.user_log(line)('Missing time limit after -t')
                return
            args = ' '.join(arg_words[2:])
        elif arg_words[0].startswith('-t'):
            self.logger.debug('Got $exec -t (2)')
            time_arg = arg_words[0][2:]
            args = ' '.join(arg_words[1:])
        else:
            time_arg = self.config['default_exec_time']
        try:
            timelimit = parse_timelimit(time_arg)
        except ValueError:
            self.user_log(line)('Invalid time limit for -t')
            return
        if timelimit > self.config['max_exec_time']:
            self.user_log(line)(f'Time limit must be <= {self.config["max_exec_time"]}')
            return
        await self.functions.exec(line, args, timelimit=timelimit)

    async def cmd_echo(self, line, cmd, args):
        """$echo command"""
        self.send_line(f'PRIVMSG {line.args[0]} :{args.rstrip()}')

    async def cmd_apt_get(self, line, cmd, args):
        """$apt-get command"""
        cmd_args = shlex.split(args)
        self.user_log(line)('Running apt-get -y ...')
        proc = await asyncio.create_subprocess_exec(
            'docker', 'exec', '-i', self.config['container_name'],
            'apt-get', '-y', *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        self.respond(line)(f'apt-get exited {proc.returncode}')
        if proc.returncode != 0:
            last_err_line = stderr.splitlines()[-1]
            self.respond(line)('apt-get: ' + last_err_line.decode('utf-8'))

    async def cmd_inspect(self, line, cmd, args):
        try:
            func_def = self.functions[args]
        except KeyError:
            self.respond(line)(f'Function "{args}" does not exist')
            return
        self.respond(line)('"{func_name}" <{func}> {func_data} -- set by {setter_nick} on {set_time}'.format(func_name=args, **func_def))

    async def cmd_restart(self, line, cmd, args):
        self.user_log(line)('Waiting for container lock ...')
        async with self.exclusive_container_control:
            self.respond(line)('Restarting container ...')
            proc = await asyncio.create_subprocess_exec(
                'docker', 'restart', self.config['container_name'],
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            ret = await asyncio.wait_for(proc.wait(), timeout=30)
            if ret == 0:
                self.respond(line)('docker restart exited 0')
            else:
                self.respond(line)(f'docker restart exited {ret} - exec functions may fail')

    async def _write_locking_control(self, line, cmd, args):
        if not self.db:
            self.logger.error('Database required for $ro/$rw')
            return
        try:
            self.config['secure_base']
            self.config['rel_secure_base']
        except KeyError:
            self.logger.error('secure_base/rel_secure_base config required for $ro/$rw')
            return

        async with self.exclusive_container_control:
            self.logger.info(f'Now have exclusive container control for ${cmd}')

            prefix = self.config['rel_secure_base'].rstrip('/') + '/'
            if args.startswith(prefix):
                args = args[len(prefix):]

            # verify the path exists and obtain the real absolute path
            proc = await asyncio.create_subprocess_exec(
                'docker', 'exec', '-i',
                '-e', f"SECURE_BASE={self.config['secure_base']}",
                '-e', f"REQUESTED_LOCK={args}",
                self.config['container_name'],
                '/home/user/write_lock.sh', 'realpath',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=3)
            try:
                stdout_line = stdout.decode('utf-8').splitlines()[0].rstrip()
            except IndexError:
                self.respond(line)('ERROR: no output when resolving path')
                return
            if not stdout_line:
                self.respond(line)('ERROR: empty result when resolving path')
                return
            if proc.returncode == 0:
                real_path = stdout_line
            else:
                self.respond(line)(f'{stdout_line} (path resolution)')
                return

            with self.db.cursor() as dbc:
                dbc.execute('SELECT owner_nick FROM write_locks WHERE file_path=%s',
                            (real_path,))
                if dbc.rowcount > 0:
                    # file is already locked
                    owner_nick, = dbc.fetchone()
                    if cmd == 'ro' or owner_nick != line.handle.nick.lower():
                        self.respond(line)(f'{line.handle.nick}: {real_path} is already locked by {owner_nick}')
                        return

            proc = await asyncio.create_subprocess_exec(
                'docker', 'exec', '-i',
                '-e', f"SECURE_BASE={self.config['secure_base']}",
                '-e', f"REQUESTED_LOCK={args}",
                self.config['container_name'],
                '/home/user/write_lock.sh', cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=3)
            try:
                stdout_line = stdout.decode('utf-8').splitlines()[0].rstrip()
            except IndexError:
                stdout_line = ''
            try:
                stderr_line = stderr.decode('utf-8').splitlines()[0].rstrip()
            except IndexError:
                stderr_line = ''
            if stderr_line:
                self.respond(line)(f'${cmd} STDERR: {stderr_line}')
            if proc.returncode == 0:
                with self.db.cursor() as dbc:
                    if cmd == 'ro':
                        dbc.execute('INSERT INTO write_locks (file_path, owner_nick) VALUES (%s, %s)',
                                    (real_path, line.handle.nick.lower()))
                    else:
                        dbc.execute('DELETE FROM write_locks WHERE file_path=%s AND owner_nick=%s',
                                    (real_path, line.handle.nick.lower()))
                        if dbc.rowcount == 0:
                            self.respond(line)(f'{line.handle.nick}: Did not find your lock on {real_path} but the file should be writable now')
                            return
                    self.db.commit()
            self.respond(line)(f'{line.handle.nick}: {stdout_line}')

    cmd_ro = _write_locking_control
    cmd_rw = _write_locking_control

    async def cmd_secret(self, line, cmd, args):
        self.respond(line)('Command $secret is only available in PM. If you just sent credentials they should be revoked and reissued.')

    async def pm_cmd_secret(self, line, cmd, args):
        if not self.db:
            self.logger.error('Database required for $secret')
            return
        args = args.split(maxsplit=2)
        set_usage = '$secret set <ENV_VAR> <value>'
        del_usage = '$secret delete <ENV_VAR>'
        all_usage = f'Usage: {set_usage} | {del_usage} | $secret list | $help for docs'
        if not args:
            self.respond(line)(all_usage)
        elif args[0] == 'set':
            try:
                var_name = args[1]
                secret_val = args[2]
            except IndexError:
                self.respond(line)(f'Missing parameter, usage: {set_usage}')
                return
            if not env_var_name_re.match(var_name) or var_name.upper().startswith('T9_'):
                self.respond(line)('Environment variable name must 1) be 4-32 characters 2) only contain letters, numbers, and underscores 3) start with a letter 4) not start with T9_')
                return
            self.logger.info(f'Setting secret value for {line.handle.nick}')
            with self.db.cursor() as dbc:
                dbc.execute('INSERT INTO secrets (owner_nick, env_var, secret) VALUES (%(nick)s, %(var)s, %(val)s) '
                            'ON CONFLICT ON CONSTRAINT secrets_pkey DO UPDATE SET secret=%(val)s', 
                            {
                                'nick': line.handle.nick,
                                'var': var_name,
                                'val': secret_val,
                            })
                self.db.commit()
            self.respond(line)('Set secret value')
        elif args[0] in ('delete', 'del', 'rm'):
            try:
                var_name = args[1]
            except IndexError:
                self.respond(line)(f'Missing parameter, usage: {del_usage}')
                return
            self.logger.info(f'Deleting secret value for {line.handle.nick}')
            with self.db.cursor() as dbc:
                dbc.execute('DELETE FROM secrets WHERE owner_nick=%s AND env_var=%s',
                            (line.handle.nick, var_name))
                if dbc.rowcount == 0:
                    self.respond(line)('You do not have a secret with that name')
                else:
                    self.respond(line)('Deleted secret')
                self.db.commit()
        elif args[0] in ('list', 'ls'):
            env_vars = []
            with self.db.cursor() as dbc:
                dbc.execute('SELECT env_var FROM secrets WHERE owner_nick=%s', (line.handle.nick,))
                for env_var, in dbc:
                    env_vars.append(env_var)
            env_vars = ', '.join(env_vars)
            self.respond(line)(f'Your secret env vars: {env_vars}')
        else:
            self.respond(line)(all_usage)

    async def pm_cmd_help(self, line, cmd, args):
        self.respond(line)(self.config['help'])

