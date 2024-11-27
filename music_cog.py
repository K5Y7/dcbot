import logging
import discord
from discord.ext import commands
from yt_dlp import YoutubeDL
from asyncio import run_coroutine_threadsafe
from urllib import parse, request
import re
import random


logging.basicConfig(level=logging.DEBUG)

class MusicCog(commands.Cog):

    # init
    def __init__(self, bot):
        self.bot = bot

        self.is_playing = {}
        self.is_paused = {}
        self.musicQueue = {}
        self.queueIndex = {}

        self.YTDL_OPTIONS = {'format': 'bestaudio', 'nonplaylist': 'True', 'vervose': True}
        self.FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}

        self.embedBlue = 0x2c76dd
        self.embedRed = 0xdf1141
        self.embedGreen = 0x0eaa51
        
        self.vc = {}

    #
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            guild_id = guild.id
            self.musicQueue[guild_id] = []
            self.queueIndex[guild_id] = 0
            self.vc[guild_id] = None
            self.is_paused[guild_id] = self.is_playing[guild_id] = False

    # auto disconnect when no users are in call
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        guild_id = member.guild.id
        if (
            member.id != self.bot.user.id and
            before.channel and
            after.channel != before.channel and
            len(before.channel.members) == 1 and
            before.channel.members[0].id == self.bot.user.id and
            self.vc[guild_id] and self.vc[guild_id].is_connected()
        ):
            self._reset_guild_state(guild_id)
            await self.vc[guild_id].disconnect()
    
    # reset state 
    def _reset_guild_state(self, guild_id):
        self.is_playing[guild_id] = self.is_paused[guild_id] = False
        self.musicQueue[guild_id] = []
        self.queueIndex[guild_id] = 0

    # generate embed for playing song
    def now_playing_embed(self, ctx, song):
        embed = discord.Embed(
            title="Now Playing",
            description=f"[{song['title']}]({song['link']})",
            colour=self.embedBlue
        )
        embed.set_thumbnail(url=song['thumbnail'])
        embed.set_footer(text=f"Song added by: {ctx.author}", icon_url=ctx.author.avatar.url)
        return embed
    
    # generate embed for adding song to queue
    def add_song_embed(self, ctx, song):
        embed = discord.Embed(
            title="Added Song To Queue",
            description=f"[{song['title']}]({song['link']})",
            colour=self.embedGreen
        )
        embed.set_thumbnail(url=song['thumbnail'])
        embed.set_footer(text=f"Song added by: {ctx.author}", icon_url=ctx.author.avatar.url)
        return embed
    
    # method for joining bot to a vc and setup
    async def join_VC(self, ctx, channel):
        guild_id = ctx.guild.id
        if self.vc.get(guild_id) is None:
            if ctx.voice_client is None:
                self.vc[guild_id] = await channel.connect()
            else:
                self.vc[guild_id] = ctx.voice_client

        if self.vc[guild_id] is not None and self.vc[guild_id].channel != channel:
            await self.vc[guild_id].move_to(channel)

    # method for getting youtube links
    def search_YT(self, search):
        queryString = parse.urlencode({'search_query': search})
        url = 'https://www.youtube.com/results?' + queryString
        htmContent = request.urlopen(url)
        searchResults = re.findall(r"watch\?v=(.{11})", htmContent.read().decode())
        return searchResults[0:1]
    
    # method for extracting data from youtube video
    def extract_YT(self, videoID):
        url = 'http://www.youtube.com/watch?v=' + videoID
        with YoutubeDL(self.YTDL_OPTIONS) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except:
                return False
        
        return {
            'link': url,
            'thumbnail': 'https://i.ytimg.com/vi/' + videoID + '/hqdefault.jpg?sqp=-oaymwEcCOADEI4CSFXyq4qpAw4IARUAAIhCGAFwAcABBg==&rs=AOn4CLD5uL4xKN-IUfez6KIW_j5y70mlig',
            'source': info['url'],
            'title': info['title']
        }
    
    # method for playing the next song
    def play_next(self, ctx):
        guild_id = ctx.guild.id
        if not self.is_playing[guild_id]:
            return
        if self.queueIndex[guild_id] + 1 < len(self.musicQueue[guild_id]):
            self.is_playing[guild_id] = True
            self.queueIndex[guild_id] += 1

            song = self.musicQueue[guild_id][self.queueIndex[guild_id]][0]
            coro = ctx.send(embed=self.now_playing_embed(ctx, song))
            fut = run_coroutine_threadsafe(coro, self.bot.loop)
            try:
                fut.result()
            except:
                pass

            self.vc[guild_id].play(discord.FFmpegPCMAudio(
                song['source'], **self.FFMPEG_OPTIONS), after=lambda e: self.play_next(ctx))
        else:
            self.is_playing[guild_id] = False

    # method for playing audio through the bot
    async def play_music(self, ctx):
        guild_id = ctx.guild.id
        if self.queueIndex[guild_id] < len(self.musicQueue[guild_id]):
            self.is_playing[guild_id] = True
            self.is_paused[guild_id] = False

            await self.join_VC(ctx, self.musicQueue[guild_id][self.queueIndex[guild_id]][1])

            song = self.musicQueue[guild_id][self.queueIndex[guild_id]][0]
            await ctx.send(embed=self.now_playing_embed(ctx, song))

            self.vc[guild_id].play(
                discord.FFmpegPCMAudio(song['source'], **self.FFMPEG_OPTIONS), after=lambda e: self.play_next(ctx))
        else:
            await ctx.send("There are no songs in the queue to be played.")
            self.is_playing[guild_id] = False
    
    @ commands.command(
        name='play',
        aliases=['pl'],
        help=""
    )
    async def play(self, ctx, *args):
        search = " ".join(args)
        guild_id = ctx.guild.id

        # In the case that the bot didnt initialize properly
        if guild_id not in self.musicQueue:
            self._reset_guild_state(guild_id)

        # Join user's channel if not already in
        try:
            userChannel = ctx.author.voice.channel
        except AttributeError:
            await ctx.send("You must be connected to a voice channel.")
            return
        
        # !play no arguments == resume
        if not args:
            if len(self.musicQueue[guild_id]) == 0:
                await ctx.send("There are no songs to be played in the queue.")
            elif not self.is_playing[guild_id] and self.vc[guild_id] and self.vc[guild_id].is_paused():
                self.vc[guild_id].resume()
                self.is_playing[guild_id] = True
                await ctx.send("Resumed ▶️")
            else:
                await ctx.send("Music is already playing.")
            return
        
        # !play with arguments
        song = self.extract_YT(self.search_YT(search)[0])
        if not song:
            await ctx.send("Could not download the song. Try different keywords.")
        else:
            self.musicQueue[guild_id].append([song, userChannel])
            if not self.is_playing[guild_id]:
                await self.play_music(ctx)
            else:
                await ctx.send(embed=self.add_song_embed(ctx, song))

    @ commands.command(
        name='pause', 
        aliases=['pa'],
        help=""
    )
    async def pause(self, ctx):
        guild_id = ctx.guild.id
        if self.vc[guild_id] and self.vc[guild_id].is_playing():
            self.vc[guild_id].pause()
            self.is_playing[guild_id] = False
            await ctx.send("Paused ⏸️")
    
    @ commands.command(
        name='skip', 
        aliases=['sk'],
        help=""
    )
    async def skip(self, ctx):
        guild_id = ctx.guild.id
        if self.vc[guild_id] and self.vc[guild_id].is_playing():
            self.vc[guild_id].stop()
            await ctx.send("Skipped ⏭️")

    @ commands.command(
        name='queue', 
        aliases=['q'],
        help=""
    )
    async def queue(self, ctx):
        guild_id = ctx.guild.id
        if len(self.musicQueue[guild_id]) <= self.queueIndex[guild_id]:
            await ctx.send(embed=discord.Embed(title="Music Queue", description="The queue is currently empty.", color=self.embedRed))
            return

        embed = discord.Embed(
            title="Music Queue",
            description=f"Showing the next {min(10, len(self.musicQueue[guild_id]) - self.queueIndex[guild_id])} songs:",
            color=self.embedBlue
        )
        for i, (song, _) in enumerate(self.musicQueue[guild_id][self.queueIndex[guild_id]:self.queueIndex[guild_id] + 10], start=1):
            embed.add_field(name=f"{i}. {song['title']}", value=f"[Link]({song['link']})", inline=False)
        await ctx.send(embed=embed)

    @ commands.command(
        name='shuffle', 
        aliases=['sh'],
        help=""
    )
    async def shuffle(self, ctx):
        guild_id = ctx.guild.id
        if len(self.musicQueue[guild_id]) <= self.queueIndex[guild_id] + 1:
            await ctx.send("The queue is currently empty.")
            return

        current_index = self.queueIndex[guild_id] + 1
        to_shuffle = self.musicQueue[guild_id][current_index:]
        random.shuffle(to_shuffle)

        # Replace the shuffled part back into the queue
        self.musicQueue[guild_id] = self.musicQueue[guild_id][:current_index] + to_shuffle
        await ctx.send("The queue has been shuffled 🎶.")

    @ commands.command(
        name='join',
        aliases=['j'],
        help=""
    )
    async def join(self, ctx):
        guild_id = ctx.guild.id

        # Ensure the user is in a voice channel
        if not ctx.author.voice:
            await ctx.send("You must be in a voice channel to use this command.")
            return

        # If the bot is already connected, move to the user channel
        user_channel = ctx.author.voice.channel
        if guild_id in self.vc and self.vc[guild_id]:
            if self.vc[guild_id].channel == user_channel:
                await ctx.send("I'm already in your voice channel!")
            else:
                await self.vc[guild_id].move_to(user_channel)
                await ctx.send(f"Moved to {user_channel.mention}.")
        else:
            self.vc[guild_id] = await user_channel.connect()
            await ctx.send(f"Joined {user_channel.mention}.")

    @ commands.command(
        name='leave',
        aliases=['l'],
        help=""
    )
    async def leave(self, ctx):
        guild_id = ctx.guild.id

        if guild_id in self.vc and self.vc[guild_id]:
            await self.vc[guild_id].disconnect()
            self._reset_guild_state(guild_id)
            self.vc[guild_id] = None
            await ctx.send("Disconnected from the voice channel.")
        else:
            await ctx.send("I'm not connected to any voice channel.")

    @ commands.command(
        name='ping'
    )
    async def ping(self, ctx):
        await ctx.send('Pong!')

    # easter egg command
    @ commands.command(
        name='des'
    )
    async def des(self, ctx):
        new_ctx = await self.bot.get_context(ctx.message)
        new_ctx.message.content = f"{ctx.prefix}play Illit Magnetic Audio"
    
        command = self.bot.get_command('play')
    
        await self.bot.invoke(new_ctx)
