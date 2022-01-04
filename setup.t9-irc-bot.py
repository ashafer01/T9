from setuptools import setup

setup(
    name='t9-irc-bot',
    version='0.3.1',
    author='Alex Shafer',
    author_email='ashafer@pm.me',
    url='https://github.com/ashafer01/t9',
    license='MIT',
    description='T9 "Anything" bot for IRC',
    long_description='T9 "Anything" bot for IRC allows user function definitions and execution on a persistent docker container',
    packages=[
        't9',
        't9_config',
    ],
    install_requires=[
        'pyyaml',
        'psycopg2',
        'aiohttp',
        'python-dataschema==0.1.4',
        'regex',
    ],
)
