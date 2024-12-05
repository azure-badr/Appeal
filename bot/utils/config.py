import os
import json

from pymongo import MongoClient

config = {}
if os.environ.get("ENVIRONMENT") == "production":
  config = {
    "MONGODB_URI": os.environ.get("MONGODB_URI"),
    "GUILD_ID": os.environ.get("GUILD_ID"),
    "BAN_APPEAL_CHANNEL_ID": os.environ.get("BAN_APPEAL_CHANNEL_ID"),
    "BAN_REASONS_CHANNEL_ID": os.environ.get("BAN_REASONS_CHANNEL_ID"),
    "CLIENT_TOKEN": os.environ.get("CLIENT_TOKEN"),
    "ENVIRONMENT": os.environ.get("ENVIRONMENT")
  }
else:
  config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.json")
  config = json.load(open(config_path))

print("Initializing database")

client = MongoClient(config["MONGODB_URI"])
if os.environ.get("ENVIRONMENT") == "DEVELOPMENT":
  database = client.appeal_dev
  print("Set appeal database to development environment")
else:
  database = client.appeal
  print("Set appeal database to production")
