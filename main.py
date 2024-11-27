import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from music_cog import MusicCog  # Ensure this matches the class name in music_cog.py

load_dotenv()

token = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Add the cog
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    await bot.add_cog(MusicCog(bot))

bot.run(token)
