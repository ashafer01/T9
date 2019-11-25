from setuptools import setup

setup(
    name='t9-exec-server',
    version='0.1.0',
    author='Alex Shafer',
    author_email='ashafer@pm.me',
    url='https://github.com/ashafer01/t9',
    license='MIT',
    description='T9 Exec Server',
    long_description='This package runs on the docker exec container',
    packages=[
        't9_exec_server',
        't9_config',
    ],
    install_requires=[
        'pyyaml',
        'aiohttp',
    ],
)
