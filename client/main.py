import time
import json
import asyncio

import requests
import urllib.parse
import urllib.request

from quart import Quart, redirect, render_template, request, session

from discord.ext import commands
import discord

from pymongo import MongoClient


config = json.load(open("config.json"))

client = MongoClient(config["MONGODB_URI"]) # os.environ.get("MONGO_URL")
database = client.appeal

intents = discord.Intents(guilds=True, members=True, bans=True)
bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)

@bot.event
async def on_ready():
    guild: discord.Guild = bot.get_guild(int(config["GUILD_ID"]))
    print(f"Online for {guild.name}")

app = Quart(__name__, static_folder="./templates")
app.secret_key = config["SECRET_KEY"] #os.environ.get("SECRET_KEY").encode()

DISCORD_CLIENT_ID = config["CLIENT_ID"] #os.environ.get("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = config["CLIENT_SECRET"] #os.environ.get("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = config["REDIRECT_URI"] #os.environ.get("DISCORD_REDIRECT_URI")

guild = None
ban_cache = {}
@app.before_serving
async def cache_setup():
    print("Running cache setup")
    global guild, ban_cache

    loop = asyncio.get_event_loop()
    await bot.login(config["CLIENT_TOKEN"])
    loop.create_task(bot.connect())

    await bot.wait_until_ready()
    guild = bot.get_guild(int(config["GUILD_ID"]))
    ban_cache = {entry.user.id: entry async for entry in guild.bans(limit=None)}
    print("Loaded ban cache", len(ban_cache))

@bot.event
async def on_member_ban(guild, user):
    ban_entry = await guild.fetch_ban(user)
    ban_cache[user.id] = ban_entry
    print("Member banned:", user.id)

@bot.event
async def on_member_unban(guild, user):
    del ban_cache[user.id]
    print("Member unbanned:", user.id)

@app.route("/")
async def home():
    if session.get("user_data") is None:
        return redirect("/login")
    
    return redirect("/profile")

@app.route("/login")
async def login():
    discord_auth_url = "https://discord.com/api/oauth2/authorize?" + urllib.parse.urlencode({
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
    })
    return redirect(discord_auth_url)

@app.route("/logout")
async def logout():
    session.pop("user_data", None)
    return "You have been logged out."

@app.route("/callback")
async def callback():
    code = request.args.get("code")
    token_request_body = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "scope": "identify"
    }
    token_response = requests.post("https://discord.com/api/oauth2/token", data=token_request_body)
    token_response.raise_for_status()
    token_data = token_response.json()
    access_token = token_data["access_token"]
    user_response = requests.get("https://discord.com/api/users/@me", headers={
        "Authorization": f"Bearer {access_token}"
    })
    user_response.raise_for_status()
    user_data = user_response.json()
    
    session["user_data"] = user_data
    
    return redirect("/profile")

@app.route("/profile")
async def profile():
    user_data = session.get("user_data")
    if user_data is None:
        return redirect("/login")
    
    user_id = int(user_data["id"])
    ban_entry = ban_cache.get(user_id)

    user_ban = database.bans.find_one({"user_id": user_id})
    user_ban_appeal_data = database.banAppeals.find_one({"user_id": user_id})

    print(ban_entry, len(ban_entry))
    # If unbanned and no current appeal
    if user_ban and ban_entry is None:
        return await render_template("profile.html", user_data=user_data, user_ban_appeal_data=user_ban_appeal_data)
    
    if ban_entry is None:
        return "You are not banned"

    if not user_ban:
        database.bans.insert_one({
            "user_id": user_id,
            "username": f"{user_data['username']}#{user_data['discriminator']}",
            "appeals": [],
            "current_appeal": None,
        })


    if user_ban_appeal_data:
        if user_ban_appeal_data.get("reappeal_time") and user_ban_appeal_data["reappeal_time"] > 0:
            user_ban_appeal_data["reappeal_time"] = round((user_ban_appeal_data["reappeal_time"] - time.time()) / (30 * 24 * 60 * 60), 2)

    return await render_template("profile.html", user_data=user_data, user_ban_appeal_data=user_ban_appeal_data, ban_entry=ban_entry)

@app.route("/appeal", methods=["POST"])
async def ban_appeal():
    user_data = session.get("user_data")
    if user_data is None:
        return redirect("/login")
    
    user_id = int(user_data["id"])
    user_ban_appeal = database.bans.find_one({"user_id": user_id})
    if user_ban_appeal.get("current"):
        return redirect("/profile")

    form = await request.form
    reason = form.get("reason")
    ban_reason = form.get("ban_reason")

    ban_appeal = database.banAppeals.insert_one({
        "user_id": user_id,
        "username": user_data["username"],
        "reason": reason,
        "ban_reason": ban_reason,
        "status": "pending",
    })

    database.bans.find_one_and_update(
        { "user_id": user_id },
        { "$set": {
            "current_appeal": ban_appeal.inserted_id,
            "appeals": user_ban_appeal["appeals"] + [ban_appeal.inserted_id]
        }
    })

    appeal_channel = bot.get_channel(int(config["BAN_APPEAL_CHANNEL_ID"]))
    message = await appeal_channel.send(
        f"**Username:** {user_data['username']}#{user_data['discriminator']}\n"
        f"**User ID:** {user_id}\n\n"
        f"**Why they think they were banned:** {ban_reason}\n"
        f"**Why they should be unbanned:** {reason}\n\n"
        "**Please use the thread to discuss this ban appeal**"
    )

    thread = await appeal_channel.create_thread(
        name=f"{user_data['username']}#{user_data['discriminator']} - {user_id}",
        message=message,
        reason=f"Ban appeal for {user_data['username']}#{user_data['discriminator']} - {user_id}",
        auto_archive_duration=10080 # 7 days
    )

    await thread.send(
        "To reject this ban appeal, use `.reject`\n"
        "To accept this ban appeal, use `.accept`\n"
        "To reject and let the user re-appeal after some months, use `.reject <number of months>`. Example: `.reject 6`\n"
        "If not specified, the default is 3 months. If the ban is permanent, use `.reject 0`."
    )

    return redirect("/profile")
