import os
import json
import datetime

import discord
from discord.ext import commands, tasks

from pymongo import MongoClient

config = {}
if os.environ.get("ENVIRONMENT") == "production":
  config = {
    "MONGODB_URI": os.environ.get("MONGODB_URI"),
    "GUILD_ID": os.environ.get("GUILD_ID"),
    "BAN_APPEAL_CHANNEL_ID": os.environ.get("BAN_APPEAL_CHANNEL_ID"),
    "MOD_ROLE_ID": os.environ.get("MOD_ROLE_ID"),
    "CLIENT_TOKEN": os.environ.get("CLIENT_TOKEN"),
    "ENVIRONMENT": os.environ.get("ENVIRONMENT")
  }
else:
  config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
  config = json.load(open(config_path))

client = MongoClient(config["MONGODB_URI"])
if os.environ.get("ENVIRONMENT") == "DEVELOPMENT":
    database = client.appeal_dev
else:
    database = client.appeal

class AppealReminder(commands.Bot):
    def __init__(self, intents):
      super().__init__(command_prefix='', intents=intents)

    async def setup_hook(self) -> None:
      # start the task to run in the background
      self.reminder.start()
      print("Started the reminder task. Will run every 24 hours.")
    
    async def on_ready(self):
      print("Logged in as", self.user.name)

    @staticmethod
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
    async def reminder(self):
      guild = self.get_guild(config["GUILD_ID"])
      ban_appeal_channel = guild.get_channel(config["BAN_APPEAL_CHANNEL_ID"])

      now = datetime.datetime.now(datetime.UTC)
      for thread in ban_appeal_channel.threads:
        thread: discord.Thread

        # Convert to offset-naive
        thread_created_at = thread.created_at.replace(tzinfo=None)
        
        # Ban appeal is 7 days old, reject and close thread
        if thread_created_at <= now - datetime.timedelta(days=7):
          print("[!] Ban appeal is 7 days old")
          print("[!] User ID", int(thread.name.split("-")[1]))
          await self.reject_appeal(thread)
          continue

        # Ban appeal is 4 days old, send a reminder to mods
        if thread_created_at <= now - datetime.timedelta(days=4):
          print("[!] Ban appeal is 4 days old")
          print("[!] User ID", int(thread.name.split("-")[1]))

          mod_role = guild.get_role(config["MOD_ROLE_ID"])
          await thread.send(
            f"{mod_role.mention}\n"
            "This ban appeal will be automatically rejected in 3 days. Please review it before then."
          )

intents = discord.Intents(members=True, guilds=True)
bot = AppealReminder(intents=intents)

if __name__ == "__main__":
  bot.run(config["CLIENT_TOKEN"])
