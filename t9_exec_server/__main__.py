import asyncio
import logging
import struct
import sys
from aiohttp import web

from .run_exec import run_exec

FMT_ID = b'\x01T91\x1d'
HEADER_STRUCT = '>5s2B2I'
MAX_LEN = 128 * 1024

logger = logging.getLogger('t9_exec_server')
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

logger.info('Exec server starting up')


async def exec_endpoint(request):
    exec_request = await request.json()

    cmd = exec_request['Cmd']
    env = exec_request.get('Env', {})
    user = exec_request.get('User')
    cwd = exec_request.get('WorkingDir')
    timeout = exec_request.get('Timeout', 10)

    logger.info(f'Received exec request cmd={cmd}')

    status = 255
    stdout = b''
    stderr = b''
    out_len = 0
    err_len = 0

    try:
        status, stdout, stderr = await run_exec(cmd, env, user, cwd, timeout)
        exc_status = 0

        stdout = stdout[:MAX_LEN]
        stderr = stderr[:MAX_LEN]

        out_len = len(stdout)
        err_len = len(stderr)

        logger.info(f'Exec finished status={status} out_len={out_len} err_len={err_len}')
    except asyncio.TimeoutError:
        exc_status = 1
        logger.info('Exec timed out')
    except Exception as e:
        exc_status = 255
        stderr = str(e).encode()
        err_len = len(stderr)
        logger.error(f'Unhandled exception during exec: {str(e)}')

    # build binary response body

    struct_fmt = HEADER_STRUCT + str(out_len) + 's' + str(err_len) + 's'
    response = struct.pack(struct_fmt, FMT_ID, exc_status, status, out_len, err_len, stdout, stderr)

    return web.Response(body=response)


async def exit_endpoint(request):
    logger.info('Got exit request')
    sys.exit(0)


async def status_endpoint(request):
    logger.info('Got status request -- status ok')
    return web.Response(text='ok')


app = web.Application()
app.add_routes([
    web.post('/exec', exec_endpoint),
    web.post('/exit', exit_endpoint),
    web.get('/status', status_endpoint),
])

web.run_app(app)
