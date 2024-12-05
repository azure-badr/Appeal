import datetime

from utils.config import config, database

import discord
from discord.ext import commands, tasks

async def reject_appeal(thread: discord.Thread):
  await thread.send("This thread has been inactive for a week. Rejecting the appeal permanently.")

  # Get user id from thread, yeah - there isn't any other way to get the appealer's id..
  try:
    user_id = int(thread.name.split("-")[1])
    updated_ban_appeal = {
      "status": "rejected",
      "attended_by": thread.owner_id, # The bot here is the owner of the thread
      "reappeal_time": 0,
      "permanent": True
    }
    ban_appeal = database.bans.find_one({"user_id": user_id})
    if ban_appeal is None:
      await thread.send("Failed to get ban appeal. Please reject manually.")
      return

    database.banAppeals.find_one_and_update(
      { "_id": ban_appeal["current_appeal"] }, 
      { "$set": updated_ban_appeal }
    )
    await thread.send(
      "This ban appeal has been automatically and permanently rejected due to inactivity.\n"
      "If you wish to change this decision, just `.accept` or `.reject <months> <remarks>` with your own duration."
    )
    await thread.edit(archived=True, locked=True)
  except ValueError as error:
    await thread.send("Failed to get user ID from thread name. Please reject manually.")
    print("Failed to get user ID from thread name", error)

@tasks.loop(hours=24)
async def reminder(bot: commands.Bot):
  guild = bot.get_guild(int(config["GUILD_ID"]))
  ban_appeal_channel = guild.get_channel(int(config["BAN_APPEAL_CHANNEL_ID"]))
  print("Got ban appeal channel", ban_appeal_channel)

  print("Checking active threads")
  print("Active threads in the ban appeal channel:", len(ban_appeal_channel.threads))

  now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
  for thread in ban_appeal_channel.threads:
    print("Processing thread", thread.name)
    thread: discord.Thread

    # Convert to offset-naive
    thread_created_at = thread.created_at.replace(tzinfo=None)
    
    # Ban appeal is 7 days old, reject and close thread
    if thread_created_at <= now - datetime.timedelta(days=7):
      print("[!] Ban appeal is 7 days old")
      print("[!] User ID", int(thread.name.split("-")[1]))
      await reject_appeal(thread)
      continue

    # Ban appeal is 4 days old or older, send a reminder to mods
    if thread_created_at <= now - datetime.timedelta(days=4):
      print("[!] The ban appeal is 4 days old or more.")
      print("[!] User ID", int(thread.name.split("-")[1]))

      mod_role = guild.get_role(config["MOD_ROLE_ID"])
      await thread.send(
        f"{mod_role.mention}\n"
        "This ban appeal is 4 days old or older and will be automatically rejected once it is a week old. Please review it before then."
      )
