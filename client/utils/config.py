import os
import json

config = {}
if os.environ.get("ENVIRONMENT") == "production":
  config = {
    "MONGODB_URI": os.environ.get("MONGODB_URI"),
    "GUILD_ID": os.environ.get("GUILD_ID"),
    "BAN_APPEAL_CHANNEL_ID": os.environ.get("BAN_APPEAL_CHANNEL_ID"),
    "CLIENT_ID": os.environ.get("CLIENT_ID"),
    "CLIENT_SECRET": os.environ.get("CLIENT_SECRET"),
    "REDIRECT_URI": os.environ.get("REDIRECT_URI"),
    "CLIENT_TOKEN": os.environ.get("CLIENT_TOKEN"),
    "ENVIRONMENT": os.environ.get("ENVIRONMENT")
  }
else:
  config = json.load(open("../config.json"))
