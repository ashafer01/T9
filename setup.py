from setuptools import setup

with open('requirements.txt') as f:
    reqs = []
    for line in f:
        reqs.append(line.strip())

setup(
    name='t9-irc-bot',
    version='0.1.0',
    description='T9 "Anything" bot for IRC',
    long_description='T9 "Anything" bot for IRC allows user function definitions and execution on a persistent docker container',
    author='Alex Shafer',
    author_email='ashafer@pm.me',
    url='https://github.com/ashafer01/t9',
    license='MIT',
    packages=['t9'],
    install_requires=reqs,
)
