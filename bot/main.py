import os
import asyncio
import time

from pymongo import MongoClient

from utils.config import config

client = MongoClient(config["MONGODB_URI"])
if os.environ.get("ENVIRONMENT") == "DEVELOPMENT":
    database = client.appeal_dev
else:
    database = client.appeal


import discord
from discord.ext import commands

intents = discord.Intents(guilds=True, members=True, messages=True, message_content=True, bans=True)
bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)


@bot.event
async def on_ready():
  guild: discord.Guild = bot.get_guild(int(config["GUILD_ID"]))
  print(f"Online for {guild.name}")

@bot.event
async def on_member_ban(guild, user):
    # If user is banned and has a current appeal, set current appeal to None

		user_ban = database.bans.find_one({"user_id": user.id})
		if user_ban and user_ban.get("current_appeal"):
				database.bans.update_one(
					{ "user_id": user.id }, 
					{ "$set": { "current_appeal": None } }
				)
		
		# Create new ban record

		ban_time = int(time.time())
		ban_entry = await guild.fetch_ban(user)
		ban_reason = ban_entry.reason

		# If banner is a bot, get the banner's reason from the ban reason
		if " | " in ban_reason:
			# Assuming the bot's reason is in the format "User | Reason"
			ban_reason_sentence = ban_reason.split(" | ")

			ban_reason = ban_reason_sentence[1]

		ban_record = {
			"user_id": user.id,
			"reason": ban_reason,
			"ban_time": ban_time,
		}

		if database.banRecords.find_one({"user_id": user.id}):
			database.banRecords.update_one({"user_id": user.id}, {"$set": ban_record})
			print("[+] New user ban record updated", ban_record)
			return
		
		database.banRecords.insert_one(ban_record)
		print("[+] New user ban record created", ban_record)

@bot.event
async def on_member_unban(guild, user):
	# If user is banned and has a current appeal, set current appeal as accepted

	user_ban = database.bans.find_one({"user_id": user.id})
	if user_ban and user_ban.get("current_appeal"):
		database.banAppeals.update_one(
			{ "_id": user_ban["current_appeal"] }, 
			{ "$set": { "status": "accepted" } }
		)


class NotBanAppealChannel(commands.CheckFailure):
	pass

def is_ban_appeal_channel():
	def predicate(ctx):
		if not isinstance(ctx.channel, discord.Thread):
			return False
		
		if not ctx.channel.parent_id == int(config["BAN_APPEAL_CHANNEL_ID"]):
			raise NotBanAppealChannel("Please use this command in a ban appeal thread.")
		
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

	ban_appeal = database.bans.find_one({"user_id": user_id})
	database.banAppeals.find_one_and_update(
		{ "_id": ban_appeal["current_appeal"] }, 
		{ "$set": updated_ban_appeal }
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
	ban_appeal = database.bans.find_one({"user_id": user_id})
	database.banAppeals.find_one_and_update(
		{ "_id": ban_appeal["current_appeal"] }, 
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
	if isinstance(error, NotBanAppealChannel):
		await ctx.send("Please use this command in a ban appeal thread.")
		return
	
	if isinstance(error, commands.MissingPermissions):
		return
	
	await ctx.send("An error occured. Please try again later.", error)

@bot.event
async def on_command_error(ctx, error):
	if isinstance(error, commands.CommandNotFound):
		return
	

bot.run(config["CLIENT_TOKEN"])
