import asyncio
import logging
import psycopg2
import signal
import ssl
import traceback

from .channels import Channels
from .commands import Commands
from .ctcp import CTCP
from .exceptions import *
from .irc import irc_reader, EOL, IRCHandler
from .user_functions import UserFunctions


async def bot(config):
    """The T9 Bot"""

    # Basic config setup

    logger = logging.getLogger(config['nick'])
    logger.debug('Starting up T9 bot')

    # Establish connection to IRC

    if config['tls']:
        ctx = ssl.SSLContext()
        ctx.set_default_verify_paths()
        if config['tls_verify']:
            ctx.verify_mode = ssl.CERT_REQUIRED
            ctx.check_hostname = True
        else:
            ctx.verify_mode = ssl.CERT_NONE
            ctx.check_hostname = False
        if config['tls_client_cert']:
            ctx.load_cert_chain(config['tls_client_cert'], config['tls_client_private_key'])
        if config['tls_ca_file'] or config['tls_ca_directory']:
            ctx.load_verify_locations(config['tls_ca_file'], config['tls_ca_directory'])
        logger.debug('TLS context configured')
    else:
        ctx = None

    reader, writer = await asyncio.open_connection(config['host'], config['port'], ssl=ctx)
    logger.debug('Connected to IRC socket')

    def send_line(line: str):
        writer.write(line.encode() + EOL)
        logger.info(f'=> {line}')

    # set up components and resources

    channels = Channels(config, send_line)
    functions = UserFunctions(config, send_line)
    ctcp = CTCP(config, send_line)

    if config['db']:
        db = psycopg2.connect(**config['db'])
        functions.load_from_db(db)
        channels.load_from_db(db)
    else:
        db = None

    sync_lock = asyncio.Lock()
    commands = Commands(config, send_line, db, functions, sync_lock)
    handshake_done = False

    # functions

    def set_up_irc_logging():
        cfg_console_level = config['console_channel_level']
        if cfg_console_level:
            level = getattr(logging, cfg_console_level.upper())
            handler = IRCHandler(writer, config['console_channel'])
            handler.setLevel(level)
            logger.addHandler(handler)
            logger.info('IRC logging online')
        else:
            logger.info('IRC logging disabled, see `console_channel_level` config option')

    async def handshake_async():
        await channels.handshake_joins()
        set_up_irc_logging()

    def finish_handshake():
        if handshake_done:
            logger.warning('Multiple calls to finish_handshake()')
            return

        for line in config['extra_handshake']:
            send_line(line)
        asyncio.create_task(handshake_async())

    async def handle_privmsg(line):
        if channels.is_ignored(line):
            logger.debug(f'Ignoring {line.handle.nick} (PRIVMSG)')
            return
        if not line.text:
            logger.debug('Message text is empty')
            return
        if len(line.args) > 1:
            logger.warning('Ignoring multi-target PRIVMSG')
            return
        if channels.is_channel(line.args[0]) and not channels.is_joined(line.args[0]):
            if config['passive_join']:
                channels.passive_join(line.args[0])
            else:
                logger.warning('Ignoring PRIVMSG for non-joined channel')
                return

        # only one component may handle a privmsg
        if commands.command_candidate(line):
            await commands.handle_privmsg(line)
        elif ctcp.ctcp_candidate(line):
            await ctcp.handle_privmsg(line)
        else:
            await functions.handle_privmsg(line)

    async def handle_line(line):
        try:
            logger.debug(f'<= {line}')
            if line.cmd == 'ERROR':
                raise FatalError('Got ERROR from server')
            elif line.cmd == 'PING':
                send_line(f'PONG :{line.text}')
            elif line.cmd == 'MODE':
                # finish the handshake after the first self-usermode that we get
                if line.args == [config['nick']] and not handshake_done:
                    finish_handshake()
                    return True  # indicate handshake is done
            elif line.cmd.isdigit():
                # Server numeric replies
                # These get dispatched to all components that handle them
                # (so far just Channels)
                await channels.handle_numeric(line)
            elif line.cmd == 'INVITE':
                await channels.handle_invite(line)
            elif line.cmd == 'KICK':
                await channels.handle_kick(line)
            elif line.cmd == 'PRIVMSG':
                await handle_privmsg(line)
            await writer.drain()
        except Exception as e:
            e_str = str(e).splitlines()[0]
            logger.error(f'Uncaught exception: {e.__class__.__name__}: {e_str}')
            logger.debug('\n' + ''.join(traceback.format_tb(e.__traceback__)))
            await writer.drain()

    # begin IRC handshake

    if config['password']:
        send_line('PASS {password}'.format(**config))
    send_line('NICK {nick}'.format(**config))
    send_line('USER {user} {vhost} {host} :{realname}'.format(**config))

    await writer.drain()

    def sigint_handler():
        send_line('QUIT :Stop Requested (SIGINT)')

    def sigterm_handler():
        send_line('QUIT :Stop Requested (SIGTERM)')

    event_loop = asyncio.get_running_loop()
    event_loop.add_signal_handler(signal.SIGINT, sigint_handler)
    event_loop.add_signal_handler(signal.SIGTERM, sigterm_handler)

    # start handling lines from the server

    async for line_obj in irc_reader(reader):
        # allow commands to prevent other lines from running concurrently
        await sync_lock.acquire()
        sync_lock.release()

        line_coro = handle_line(line_obj)
        if not handshake_done:
            # handle lines synchronously until the handshake is complete
            handshake_done = await line_coro
        else:
            # handle lines asynchronously
            asyncio.create_task(line_coro)
