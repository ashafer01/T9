import asyncio
from itertools import chain
from .components import Component
from .exceptions import FatalError

JOIN_RESPONSE_WAIT_SECONDS = 10
KICK_REJOIN_WAIT_SECONDS = 5

JOIN_SUCCESS_NUMERICS = {'331', '332', '366'}
JOIN_FAIL_NUMERICS = {'403', '405', '471', '473', '474', '475', '476'}


class Channels(Component):
    def __init__(self, config, send_line):
        Component.__init__(self, config)
        self._invite_channels = set()
        self._db_channels = set()
        self._joined_channels = set()
        self._joining_channels = {}
        self.db = None
        self.send_line = send_line

    def load_from_db(self, db):
        self.db = db
        self._invite_channels.clear()
        with db.cursor() as dbc:
            dbc.execute('SELECT channel FROM chans')
            for channel, in dbc:
                if channel in self.config['channels']:
                    self.logger.warning(f'Channel {channel} is in both the database and config')
                    continue
                self._invite_channels.add(channel)
                self._db_channels.add(channel)

    def is_joined(self, channel):
        return channel.lower() in self._joined_channels

    def passive_join(self, channel):
        # for when we get a message for a channel we're not joined to
        # allows SVSJOIN to work but may potentially pose a security risk on some servers
        self.logger.info(f'Received message on un-joined channel {channel} -- marking as joined')
        self._joined_channels.add(channel.lower())

    def _is_conf_channel(self, channel):
        return channel in self.config['channels']

    async def _join_wait(self, channel):
        self.send_line(f'JOIN {channel}')
        await asyncio.sleep(JOIN_RESPONSE_WAIT_SECONDS)

        # expect task to be cancelled before we get here
        self._join_fail(channel)
        self.logger.error(f'Time out waiting for response to joining {channel}')

    def _join(self, channel):
        coro = self._join_wait(channel)
        task = asyncio.create_task(coro)
        self._joining_channels[channel] = task
        return task

    def _joining_stopped(self, channel):
        self._joining_channels[channel].cancel()
        del self._joining_channels[channel]

    def _join_success(self, channel):
        self._joining_stopped(channel)
        if self.db and channel in self._invite_channels and channel not in self._db_channels:
            with self.db.cursor() as dbc:
                dbc.execute('INSERT INTO chans (channel) VALUES (%s)', (channel,))
                self.db.commit()
                self._db_channels.add(channel)
                self.logger.debug(f'Persisted invite channel {channel} in db')
        self._joined_channels.add(channel)

    def _join_fail(self, channel):
        self._joining_stopped(channel)
        self._invite_channels.discard(channel)

    async def handshake_joins(self):
        joins = []
        for channel in chain(self.config['channels'], self._invite_channels):
            joins.append(self._join(channel))
        await asyncio.gather(*joins, return_exceptions=True)
        if not self.is_joined(self.config['console_channel']):
            raise FatalError('Console channel is not joined')
        else:
            self.logger.debug('Handshake joins have all been responded to')

    async def handle_numeric(self, line):
        if line.cmd not in JOIN_SUCCESS_NUMERICS and line.cmd not in JOIN_FAIL_NUMERICS:
            return

        channel = line.args[1].lower()

        if self.is_joined(channel):
            return

        if line.cmd in JOIN_SUCCESS_NUMERICS:
            self._join_success(channel)
            self.logger.info(f'Successfully joined channel {channel} ({line.cmd})')
        elif line.cmd in JOIN_FAIL_NUMERICS:
            self._join_fail(channel)
            self.logger.error(f'Failed to join {channel}: ({line.cmd}) {line.text}')

    async def handle_invite(self, line):
        if line.args[0].lower() != self.config['nick'].lower():
            return

        inv_channel = line.text.lower()

        # gate the invite
        if inv_channel in self.config['channels']:
            self.logger.info(f'Channel {inv_channel} is always joined')
            return
        if self.is_joined(inv_channel):
            self.logger.info(f'Already joined to {inv_channel} ignoring invite')
            return
        invite_allowed = self.config['invite_allowed']
        if invite_allowed is False:
            self.logger.info(f'Invites are disabled ignoring invite to {inv_channel} from {line.handle.nick}')
            return
        elif not invite_allowed:
            # invites open to everyone except global ignores
            if self.is_ignored(line):
                self.logger.debug(f'Ignoring {line.handle.nick} (invite)')
                return
        else:
            # invites restricted
            if line.handle.nick not in invite_allowed:
                self.logger.warning(f'Invitation to {inv_channel} from {line.handle.nick} not allowed')
                return

        # join the channel
        self.logger.info(f"Joining {inv_channel} due to invite from {line.handle.nick}")
        self._invite_channels.add(inv_channel)
        self._join(inv_channel)

    async def handle_kick(self, line):
        if line.args[1].lower() != self.config['nick'].lower():
            return

        channel = line.args[0].lower()

        self._joined_channels.remove(channel)
        if self._is_conf_channel(channel):
            self.logger.info(f'Kicked from conf channel {channel} by {line.handle.nick}')
            while not self.is_joined(channel):
                await asyncio.sleep(KICK_REJOIN_WAIT_SECONDS)
                self.logger.info(f'Attempting rejoin to kicked conf channel {channel}')
                self._join(channel)
        elif channel in self._invite_channels:
            if self.db and channel in self._db_channels:
                with self.db.cursor() as dbc:
                    dbc.execute('DELETE FROM chans WHERE channel=%s', (channel,))
                    self.db.commit()
                    self._db_channels.remove(channel)
                    self.logger.debug(f'Removed invite channel {channel} from db')
            self._invite_channels.remove(channel)
            self.logger.info(f'Kicked from invited channel {channel} by {line.handle.nick}')
        else:
            self.logger.info(f'Kicked from passive-joined channel {channel} by {line.handle.nick}')
