import asyncio
import aiohttp
import struct
from typing import List, Dict

from .utils import Component

FMT_ID = b'\x01T91\x1d'
HEADER_STRUCT = '>5s2B2I'
HEADER_SIZE = struct.calcsize(HEADER_STRUCT)


class ServerExecSession(Component):
    def __init__(self, config):
        Component.__init__(self, config)
        self.base_url = self.config['exec_server_base_url']

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, etype, e, trace):
        await self.session.close()

    def unpack_output(self, res_data):
        fmt_id, exc_status, status, out_len, err_len = struct.unpack(HEADER_STRUCT, res_data[:HEADER_SIZE])
        if fmt_id != FMT_ID:
            raise Exception(f'Unknown response format ID, got {fmt_id} expected {FMT_ID}')
        self.logger.debug(f'Got response: exc_status={exc_status} status={status} out_len={out_len} err_len={err_len}')
        struct_fmt = str(out_len) + 's' + str(err_len) + 's'
        stdout, stderr = struct.unpack_from(struct_fmt, res_data, offset=HEADER_SIZE)
        return exc_status, status, stdout, stderr

    async def exec(self, args: List[str], env: Dict[str, str] = None, user: str = None, cwd: str = None, timeout: int = None):
        params = {'Cmd': args}
        if env:
            params['Env'] = env
        if user:
            params['User'] = user
        if cwd:
            params['WorkingDir'] = cwd
        if timeout:
            params['Timeout'] = timeout  # server-side timeout -- actual exec time limit

        exec_url = self.base_url + '/exec'
        self.logger.debug(f'Sending exec request to {exec_url} {repr(params)}')
        res = await self.session.post(
            exec_url,
            json=params,
            timeout=timeout+3,  # client-side timeout with tolerance for transmission delay, etc.
        )
        res.raise_for_status()
        exc_status, status, stdout, stderr = self.unpack_output(await res.read())
        if exc_status == 0:
            pass
        elif exc_status == 1:
            self.logger.debug('exec timed out on server side')
            raise asyncio.TimeoutError()
        elif exc_status == 255:
            stderr = stderr.decode('utf-8')
            raise Exception(f'Unhandled exception during exec on server: {stderr}')
        else:
            raise Exception(f'Unknown exception status from server ({exc_status})')
        return status, stdout, stderr

    async def exit(self):
        try:
            await self.session.post(self.base_url + '/exit')
        except Exception:
            # we're telling the server to abruptly exit
            # probly wont get a valid response
            pass

    async def status(self, timeout):
        res = await self.session.get(self.base_url + '/status', timeout=timeout)
        res.raise_for_status()
        status = await res.text()
        if not status:
            return '<empty>'
        else:
            return status
