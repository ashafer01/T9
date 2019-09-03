"""
For handling the IRC protocol
"""

import collections
import re
import logging

EOL = b'\r\n'


class Line(object):
    def __init__(self):
        self.prefix = None
        self.cmd = None
        self.args = []
        self.text = ''
        self.raw = None
        self.bytes = None
        self.handle = HandleInfo()

    @classmethod
    def parse(cls, bytes_line, encoding='utf-8'):
        line = bytes_line.decode(encoding)
        ret = cls()
        ret.bytes = bytes_line
        ret.raw = line
        tokens = collections.deque(line.strip().split(' '))
        if tokens[0][0:1] == ':':
            ret.prefix = tokens.popleft()[1:]
            ret.handle = HandleInfo.parse(ret.prefix)
        ret.cmd = tokens.popleft()
        text_words = []
        ontext = False
        for token in tokens:
            if not ontext:
                if token.strip() == '':
                    continue
                if token.lstrip()[0:1] == ':':
                    ontext = True
                    text_words.append(token.lstrip()[1:])
                else:
                    ret.args.append(token.strip())
            else:
                text_words.append(token)
        ret.text = ' '.join(text_words)
        return ret

    def __str__(self):
        if self.raw is None:
            ret = []
            if self.prefix is not None:
                ret.append(':' + self.prefix)
            ret.append(self.cmd)
            ret += self.args
            if self.text is not None:
                ret.append(':' + self.text)
            return ' '.join(ret)
        else:
            return self.raw

    def __bytes__(self):
        if self.bytes is None:
            return str(self).encode()
        else:
            return self.bytes


class HandleInfo(object):
    def __init__(self):
        self.nick = None
        self.user = None
        self.host = None

    @classmethod
    def parse(cls, handle):
        match = re.search('^([^!]+)!([^@]+)@(.+)$', handle.strip())
        ret = cls()
        if match is not None:
            ret.nick = match.group(1)
            ret.user = match.group(2)
            ret.host = match.group(3)
        return ret

    def __str__(self):
        return '{nick}!{user}@{host}'.format(**self.__dict__)


async def line_reader(reader, read_buffer=512):
    buffer = b''
    while not reader.at_eof():
        buffer += await reader.read(read_buffer)
        lines = buffer.split(EOL)
        if len(lines) == 1:  # if no EOL
            continue
        buffer = lines.pop()  # b'' if we ended with EOL, partial line otherwise
        for raw_line in lines:
            yield raw_line


async def irc_reader(reader, encoding='utf-8', read_buffer=512):
    async for bytes_line in line_reader(reader, read_buffer):
        line_obj = Line.parse(bytes_line)
        yield line_obj


class IRCHandler(logging.StreamHandler):
    """Logging handler that emits messages on a stream in IRC protocol"""
    def __init__(self, stream, channel):
        logging.StreamHandler.__init__(self, stream)
        self.channel = channel.encode()

    def emit(self, record):
        try:
            msg = self.format(record).encode()

            levelstr = record.levelname
            if levelstr == 'ERROR':
                cc = b'04'  # red
            elif levelstr == 'CRITICAL':
                cc = b'04'  # red
                levelstr = 'CRIT'
            elif levelstr == 'WARNING':
                cc = b'08'  # yellow
                levelstr = 'WARN'
            else:
                cc = b'11'  # cyan
            levelprefix = format(levelstr, '>5').encode()
            color = b'\x03'
            prefix = color + cc + levelprefix + color + b' '

            self.stream.write(b'PRIVMSG ' + self.channel + b' :' + prefix + msg + EOL)
            self.flush()
        except Exception:
            self.handleError(record)
