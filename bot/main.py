import json
import asyncio
import time

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
async def reject(ctx, duration_in_months=3):
	thread = ctx.channel

	original_duration_in_months = duration_in_months
	duration_in_months = int(duration_in_months)

	if not duration_in_months == 0:
		duration_in_months = int(time.time() + (duration_in_months * 30 * 24 * 60 * 60))

	user_id = int(thread.name.split(" - ")[1])

	updated_ban_appeal = {
		"status": "rejected",
		"attended_by": ctx.author.id,
		"reappeal_time": duration_in_months,
		"permanent": False
	}

	if original_duration_in_months == 0:
		updated_ban_appeal["permanent"] = True

	database.banAppeals.update_one(
		{ "user_id": user_id }, 
		{ "$set": updated_ban_appeal }
	)

	database.bans.update_one(
		{ "user_id": user_id }, 
		{ "$set": { "current_appeal": None } }
	)

	await thread.send(
		"This ban appeal has been rejected. "
		f"{'This ban is permanent.' if original_duration_in_months == 0 else f'The user can re-appeal after {original_duration_in_months} months.'}"
	)
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

	# Send reference to thread to ban-reasons channel
	ban_reasons_channel = ctx.guild.get_channel(int(config["BAN_REASONS_CHANNEL_ID"]))

	await asyncio.sleep(6)
	await ban_reasons_channel.send(f"{thread.mention}")

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