import json

from pymongo import MongoClient

config = json.load(open("config.json"))

client = MongoClient(config["MONGODB_URI"]) # os.environ.get("MONGO_URL")
database = client.appeal

import discord
from discord.ext import commands

intents = discord.Intents(guilds=True, members=True, messages=True, message_content=True)
bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)


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
	thread = ctx.channel

	user_id = int(thread.name.split(" - ")[1])
	database.banAppeals.update_one(
		{ "user_id": user_id }, 
		{ "$set": { 
				"status": "rejected", 
				"attended_by": ctx.author.id
			}
		}
	)

	await thread.send("This ban appeal has been rejected.")
	await thread.edit(locked=True, archived=True)

@bot.command()
@is_ban_appeal_channel()
@commands.has_permissions(ban_members=True)
async def accept(ctx):
	thread = ctx.channel

	user_id = int(thread.name.split(" - ")[1])
	database.banAppeals.update_one(
		{ "user_id": user_id }, 
		{ "$set": { 
				"status": "accepted", 
				"attended_by": ctx.author.id
			}
		}
	)

	try:
		user = await bot.fetch_user(user_id)
		await ctx.guild.unban(user)
	except Exception as error:
		await thread.send(error)

	await thread.send("This ban appeal has been accepted. The user has been unbanned")
	await thread.edit(locked=True, archived=True)

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