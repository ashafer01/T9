import asyncio
import os.path
import shlex

from .utils import InterfaceComponent


class CTCP(InterfaceComponent):
    @staticmethod
    def ctcp_candidate(line):
        return line.text.startswith('\x01') and line.text.endswith('\x01')

    async def handle_line(self, line):
        # got CTCP
        ctcp_args = shlex.split(line.text.strip('\x01'))
        ctcp_cmd = ctcp_args[0].upper()
        if ctcp_cmd == 'DCC':
            try:
                self.config['dcc_max_size']
                self.config['dcc_dir']
            except KeyError:
                self.logger.error('dcc_dir/dcc_max_size config required for DCC')
                return
            dcc_cmd = ctcp_args[1]
            if dcc_cmd == 'SEND':
                # got DCC file transfer request
                def pm_status(msg):
                    self.send_line(f'PRIVMSG {line.handle.nick} :{msg}')

                dcc_file_size = int(ctcp_args[5])
                if dcc_file_size > self.config['dcc_max_size']:
                    pm_status(f'Ignoring DCC SEND from {line.handle.nick} because file is over size limit '
                              f'{self.config["dcc_max_size"]}')
                else:
                    dcc_file = os.path.basename(ctcp_args[2])
                    dcc_port = int(ctcp_args[4])

                    dcc_ip_int = int(ctcp_args[3])
                    dcc_ip_bytes = dcc_ip_int.to_bytes(4, byteorder='big')
                    dcc_ip = '.'.join([str(int(b)) for b in dcc_ip_bytes])

                    pm_status(f'Receiving DCC SEND of {dcc_file} from {line.handle.nick} on {dcc_ip}:{dcc_port}')

                    dcc_reader, dcc_writer = await asyncio.open_connection(dcc_ip, dcc_port, limit=dcc_file_size)
                    with open(os.path.join(self.config['dcc_dir'], dcc_file), 'wb') as f:
                        received_size = 0
                        while not dcc_reader.at_eof():
                            dcc_file_contents = await dcc_reader.read(dcc_file_size)
                            received_size += len(dcc_file_contents)
                            dcc_writer.write(received_size.to_bytes(4, byteorder='big'))
                            if received_size > dcc_file_size + 1:
                                pm_status('DCC SEND from {line.handle.nick} on {dcc_ip}:{dcc_port} truncated '
                                          'due to exceeding declared size')
                                break
                            f.write(dcc_file_contents)
                    dcc_writer.close()

                    pm_status(f'DCC SEND of {dcc_file} from {line.handle.nick} completed successfully')
            else:
                self.logger.debug(f'Unhandled DCC command {dcc_cmd}')
        else:
            self.logger.debug(f'Unhandled CTCP command {ctcp_cmd}')
