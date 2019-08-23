import asyncio
import logging
import os.path
import psycopg2
import re
import shlex
import traceback
from collections import deque
from datetime import datetime

from .commands import Commands
from .irc import irc_reader, EOL, IRCHandler
from .exceptions import *
from .user_functions import UserFunctions
from .utils import parse_timelimit

env_var_name_re = re.compile('^[a-zA-Z][a-zA-Z0-9_]{3,31}$')


async def bot(config):
    """The T9 Bot"""

    # Basic config setup

    logger = logging.getLogger(config['nick'])

    config.setdefault('exec_locale', 'C')
    config.setdefault('exec_python_utf8', True)
    config.setdefault('ignore', [])
    config['ignore'] = [nick.lower() for nick in config['ignore']]

    console_channel = config.setdefault('console_channel', '#{nick}-console'.format(**config))
    if console_channel not in config['channels']:
        config['channels'].append(console_channel)

    config['function_exec_time'] = parse_timelimit(config.get('function_exec_time', '10s'))
    config['max_exec_time'] = parse_timelimit(config.get('max_exec_time', '1h'))
    config['default_exec_time'] = parse_timelimit(config.get('default_exec_time', '10s'))

    # Establish connection to IRC

    reader, writer = await asyncio.open_connection(config['host'], config['port'])

    def send_line(line):
        writer.write(line.encode() + EOL)
        logger.info(f'=> {line}')

    # set up resources

    functions = UserFunctions(config, logger, send_line)

    if 'db' in config:
        db = psycopg2.connect(
            dbname=config['db']['dbname'],
            user=config['db']['user'],
            password=config['db']['password'],
            host=config['db']['host'],
        )

        functions.load_from_db(db)

        with db.cursor() as dbc:
            dbc.execute('SELECT channel FROM chans')
            for channel, in dbc:
                if channel not in config['channels']:
                    config['channels'].append(channel)
    else:
        db = None

    sync_lock = asyncio.Lock()
    commands = Commands(config, logger, db, functions, sync_lock, send_line)

    async def line_task(line):
        logger.debug(f'<= {line}')
        if line.cmd == 'ERROR':
            raise FatalError('Got ERROR from server')
        elif line.cmd == 'PING':
            send_line(f'PONG :{line.text}')
        elif line.cmd == 'MODE':
            if line.args == [config['nick']] and not handshake_done:
                # after the first self-usermode that we get, join channels and
                # mark the handshake complete; this causes lines to begin
                # asyncronous handling
                for channel in config['channels']:
                    send_line(f'JOIN {channel}')

                cfg_console_level = config.get('console_channel_level', 'INFO')
                if cfg_console_level:
                    level = getattr(logging, cfg_console_level.upper())
                    handler = IRCHandler(writer, console_channel)
                    handler.setLevel(level)
                    logger.addHandler(handler)
                    logger.info('IRC logging online')
                else:
                    logger.info('IRC logging disabled, see `console_channel_level` config option')

                return True  # indicate handshake is done
        elif line.cmd == 'INVITE':
            inv_channel = line.text
            invite_allowed = config.get('invite_allowed')
            if invite_allowed is False:
                logger.info('Invites are disabled')
                return
            elif not invite_allowed:
                # invites open to everyone except global ignores
                if line.handle.nick.lower() in config['ignore']:
                    logger.debug(f'Ignoring {line.handle.nick} (invite)')
                    return
            else:
                # invites restricted
                if line.handle.nick not in invite_allowed:
                    logger.warn(f'Invitation to {inv_channel} from {line.handle.nick} not allowed')
                    return
            if inv_channel not in config['channels']:
                if db:
                    with db.cursor() as dbc:
                        dbc.execute('INSERT INTO chans (channel) VALUES (%s)',
                                    (inv_channel,))
                        db.commit()
                config['channels'].append(inv_channel)
                send_line(f'JOIN {line.text}')
            else:
                logger.info(f'Already joined to {inv_channel} ignoring invite')
        elif line.cmd == 'PRIVMSG':
            if line.handle.nick.lower() in config['ignore']:
                logger.debug(f'Ignoring {line.handle.nick} (privmsg)')
                return
            if commands.channel_command_candidate(line):
                await commands.handle_line(line)
            elif line.text[0] == '\x01':
                # got CTCP
                ctcp_args = shlex.split(line.text.strip('\x01'))
                ctcp_cmd = ctcp_args[0].upper()
                if ctcp_cmd == 'DCC':
                    try:
                        config['dcc_max_size']
                        config['dcc_dir']
                    except KeyError:
                        logger.error('dcc_dir/dcc_max_size config required for DCC')
                        return
                    dcc_cmd = ctcp_args[1]
                    if dcc_cmd == 'SEND':
                        # got DCC file transfer request
                        def pm_status(msg):
                            send_line(f'PRIVMSG {line.handle.nick} :{msg}')

                        dcc_file_size = int(ctcp_args[5])
                        if dcc_file_size > config['dcc_max_size']:
                            pm_status(f'Ignoring DCC SEND from {line.handle.nick} because file is over size limit {config["dcc_max_size"]}')
                        else:
                            dcc_file = os.path.basename(ctcp_args[2])
                            dcc_port = int(ctcp_args[4])

                            dcc_ip_int = int(ctcp_args[3])
                            dcc_ip_bytes = dcc_ip_int.to_bytes(4, byteorder='big')
                            dcc_ip = '.'.join([str(int(b)) for b in dcc_ip_bytes])

                            pm_status(f'Receiving DCC SEND of {dcc_file} from {line.handle.nick} on {dcc_ip}:{dcc_port}')

                            dcc_reader, dcc_writer = await asyncio.open_connection(dcc_ip, dcc_port, limit=dcc_file_size)
                            with open(os.path.join(config['dcc_dir'], dcc_file), 'wb') as f:
                                received_size = 0
                                while not dcc_reader.at_eof():
                                    dcc_file_contents = await dcc_reader.read(dcc_file_size)
                                    received_size += len(dcc_file_contents)
                                    if received_size > dcc_file_size + 1:
                                        pm_status('DCC SEND from {line.handle.nick} on {dcc_ip}:{dcc_port} truncated due to exceeding declared size')
                                        break
                                    f.write(dcc_file_contents)
                            dcc_writer.close()

                            pm_status(f'DCC SEND of {dcc_file} from {line.handle.nick} completed successfully')
                    else:
                        logger.debug(f'Unhandled DCC command {dcc_cmd}')
                else:
                    logger.debug(f'Unhandled CTCP command {ctcp_cmd}')
            elif commands.pm_command_candidate(line):
                logger.debug(f'Trying PM command from {line.handle.nick}')
                await commands.handle_line(line)
            elif line.args[0][0] != '#':
                logger.debug(f'Ignoring PM from {line.handle.nick}')
                return
            else:
                # check if the line contains a function definition
                # define it if it does
                # if it doesnt, check if it contains a function trigger
                # run the function if it does
                await functions.handle_line(line)

    async def safe_await(aw, cls=Exception):
        try:
            ret = await aw
            await writer.drain()
            return ret
        except cls as e:
            e_str = str(e).splitlines()[0]
            logger.error(f'Uncaught exception: {e.__class__.__name__}: {e_str}')
            logger.debug('\n' + ''.join(traceback.format_tb(e.__traceback__)))
            await writer.drain()

    try:
        send_line('PASS {password}'.format(**config))
    except KeyError:
        pass
    send_line('NICK {nick}'.format(**config))
    send_line('USER {user} {vhost} {host} :{realname}'.format(**config))

    await writer.drain()

    handshake_done = False
    async for line in irc_reader(reader):
        # allow commands to prevent other lines from running concurrently
        await sync_lock.acquire()
        sync_lock.release()

        line_coro = safe_await(line_task(line))
        if not handshake_done:
            handshake_done = await line_coro
        else:
            task = asyncio.create_task(line_coro)
