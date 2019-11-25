import asyncio
from t9_config import config

from .bot import bot

asyncio.run(bot(config), debug=True)
