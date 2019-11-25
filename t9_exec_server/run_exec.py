"""A Docker-API-inspired exec interface"""
import asyncio
import grp
import os
import pwd
from typing import List, Dict

NOBODY_GID = 65534
PIPE = asyncio.subprocess.PIPE
USER_VARS = ('USER', 'USERNAME', 'LOGNAME')


def become_uid(uid, gid, exec_env=None):
    user = pwd.getpwuid(uid).pw_name
    if exec_env is not None:
        for user_var in USER_VARS:
            exec_env[user_var] = user

    def do_become():
        for user_var in USER_VARS:
            os.environ[user_var] = user
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)
        os.umask(0o077)
    return do_become


def user_spec_to_uid_gid(user_spec_val):
    user_spec_val = str(user_spec_val)
    try:
        user_val, grp_val = user_spec_val.split(':')
        try:
            gid = int(grp_val)
        except ValueError:
            try:
                gid = grp.getgrnam(grp_val).gr_gid
            except KeyError:
                raise Exception('No such group name {}'.format(grp_val))
    except ValueError:
        # we only got a user value
        user_val = user_spec_val
        gid = NOBODY_GID

    try:
        uid = int(user_val)
    except ValueError:
        try:
            uid = pwd.getpwnam(user_val).pw_uid
        except KeyError:
            raise Exception('No such user name {}'.format(user_val))

    return uid, gid


async def run_exec(cmd: List[str], env: Dict[str, str], user: str = None, cwd: str = None, timeout: int = 10):
    """Run an exec request"""
    kwds = {
        'cwd': cwd,
        'env': env,
        'stdout': PIPE,
        'stderr': PIPE,
    }

    if user:
        uid, gid = user_spec_to_uid_gid(user)
        kwds['preexec_fn'] = become_uid(uid, gid, kwds['env'])

    p = await asyncio.create_subprocess_exec(*cmd, **kwds)
    stdout, stderr = await asyncio.wait_for(p.communicate(), timeout=timeout)
    return p.returncode, stdout, stderr
