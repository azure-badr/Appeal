import json

from discord.ext import commands
import discord

intents = discord.Intents(guilds=True, members=True, messages=True, message_content=True)
bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)

config = json.load(open("config.json"))

@bot.event
async def on_ready():
  guild: discord.Guild = bot.get_guild(int(config["GUILD_ID"]))
  print(f"Online for {guild.name}")


# Make separate check predicate for ban appeal channel
def is_ban_appeal_channel():
	def predicate(ctx):
		if not isinstance(ctx.channel, discord.Thread):
			return False
		
		if not ctx.channel.parent_id == int(config["BAN_APPEAL_CHANNEL_ID"]):
			return False
		
		return True
	
	return commands.check(predicate)

@bot.command()
@is_ban_appeal_channel()
@commands.has_permissions(ban_members=True)
async def reject(ctx):
	await ctx.send("Test")

@bot.command()
@is_ban_appeal_channel()
@commands.has_permissions(ban_members=True)
async def accept(ctx):
	await ctx.send("Test")

@reject.error
@accept.error
async def ban_appeal_error(ctx, error):
	if isinstance(error, commands.CheckFailure):
		await ctx.send("Please use this command in a ban appeal thread.")
		return

@bot.event
async def on_command_error(ctx, error):
	if isinstance(error, commands.CommandNotFound):
		return
	

bot.run(config["CLIENT_TOKEN"])