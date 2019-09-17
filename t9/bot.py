import asyncio
import logging
import psycopg2
import signal
import traceback

from .commands import Commands
from .ctcp import CTCP
from .exceptions import *
from .irc import irc_reader, EOL, IRCHandler
from .user_functions import UserFunctions
from .utils import parse_timelimit


async def bot(config):
    """The T9 Bot"""

    # Basic config setup

    logger = logging.getLogger(config['nick'])

    config.setdefault('exec_locale', 'C')
    config.setdefault('exec_python_utf8', True)
    config.setdefault('ignore', [])
    config['ignore'] = [nick.lower() for nick in config['ignore']]

    config.setdefault('channels', [])
    console_channel = config.setdefault('console_channel', '#{nick}-console'.format(**config))
    if console_channel not in config['channels']:
        config['channels'].append(console_channel)

    config['function_exec_time'] = parse_timelimit(config.get('function_exec_time', '10s'))
    config['max_exec_time'] = parse_timelimit(config.get('max_exec_time', '1h'))
    config['default_exec_time'] = parse_timelimit(config.get('default_exec_time', '10s'))

    # Establish connection to IRC

    reader, writer = await asyncio.open_connection(config['host'], config['port'])

    def send_line(line: str):
        writer.write(line.encode() + EOL)
        logger.info(f'=> {line}')

    # set up resources

    functions = UserFunctions(config, send_line)

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

    handshake_done = False
    sync_lock = asyncio.Lock()
    commands = Commands(config, send_line, db, functions, sync_lock)
    ctcp = CTCP(config, send_line)

    # functions

    def is_ignored(line):
        return line.handle.nick.lower() in config['ignore']

    async def handle_invite(line):
        inv_channel = line.text

        # gate the invite
        invite_allowed = config.get('invite_allowed')
        if invite_allowed is False:
            logger.info('Invites are disabled')
            return
        elif not invite_allowed:
            # invites open to everyone except global ignores
            if is_ignored(line):
                logger.debug(f'Ignoring {line.handle.nick} (invite)')
                return
        else:
            # invites restricted
            if line.handle.nick not in invite_allowed:
                logger.warning(f'Invitation to {inv_channel} from {line.handle.nick} not allowed')
                return

        # join the channel
        if inv_channel not in config['channels']:
            if db:
                with db.cursor() as dbc:
                    dbc.execute('INSERT INTO chans (channel) VALUES (%s)', (inv_channel,))
                    db.commit()
            config['channels'].append(inv_channel)
            send_line(f'JOIN {line.text}')
        else:
            logger.info(f'Already joined to {inv_channel} ignoring invite')

    def join_channels():
        for channel in config['channels']:
            send_line(f'JOIN {channel}')

    def set_up_irc_logging():
        if handshake_done:
            logger.warning('Multiple calls to set_up_irc_logging()')
            return

        cfg_console_level = config.get('console_channel_level', 'INFO')
        if cfg_console_level:
            level = getattr(logging, cfg_console_level.upper())
            handler = IRCHandler(writer, console_channel)
            handler.setLevel(level)
            logger.addHandler(handler)
            logger.info('IRC logging online')
        else:
            logger.info('IRC logging disabled, see `console_channel_level` config option')

    async def line_task(line):
        logger.debug(f'<= {line}')
        if line.cmd == 'ERROR':
            raise FatalError('Got ERROR from server')
        elif line.cmd == 'PING':
            send_line(f'PONG :{line.text}')
        elif line.cmd == 'MODE':
            if line.args == [config['nick']] and not handshake_done:
                # finish the handshake after the first self-usermode that we get
                join_channels()
                set_up_irc_logging()
                return True  # indicate handshake is done
        elif line.cmd == 'INVITE':
            await handle_invite(line)
        elif line.cmd == 'PRIVMSG':
            if is_ignored(line):
                logger.debug(f'Ignoring {line.handle.nick} (privmsg)')
                return

            if commands.command_candidate(line):
                await commands.handle_line(line)
            elif ctcp.ctcp_candidate(line):
                await ctcp.handle_line(line)
            else:
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

    # begin IRC handshake

    try:
        send_line('PASS {password}'.format(**config))
    except KeyError:
        pass
    send_line('NICK {nick}'.format(**config))
    send_line('USER {user} {vhost} {host} :{realname}'.format(**config))

    await writer.drain()

    def sigint_handler():
        send_line('QUIT :Stop Requested')

    asyncio.get_running_loop().add_signal_handler(signal.SIGINT, sigint_handler)

    # start handling lines from the server

    async for line_obj in irc_reader(reader):
        # allow commands to prevent other lines from running concurrently
        await sync_lock.acquire()
        sync_lock.release()

        line_coro = safe_await(line_task(line_obj))
        if not handshake_done:
            # handle lines synchronously until the handshake is complete
            handshake_done = await line_coro
        else:
            # handle lines asynchronously
            asyncio.create_task(line_coro)
