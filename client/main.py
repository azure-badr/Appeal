import os
import time
import asyncio
import datetime

import requests
import urllib.parse
import urllib.request

from quart import Quart, redirect, render_template, request, session, abort, make_response

from discord.ext import commands
import discord

from pymongo import MongoClient

client = MongoClient(os.environ.get("MONGODB_URI")) 
database = client.appeal

intents = discord.Intents(guilds=True, members=True, bans=True)
bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)

GUILD_ID = int(os.environ.get("GUILD_ID"))
BAN_APPEAL_CHANNEL_ID = int(os.environ.get("BAN_APPEAL_CHANNEL_ID"))
@bot.event
async def on_ready():
    guild: discord.Guild = bot.get_guild(GUILD_ID)
    print(f"Online for {guild.name}")

app = Quart(__name__, static_folder="./templates")
app.secret_key = os.urandom(24)

DISCORD_CLIENT_ID = os.environ.get("CLIENT_ID")
DISCORD_CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.environ.get("REDIRECT_URI")
CLIENT_TOKEN = os.environ.get("CLIENT_TOKEN")

guild = None
ban_cache = {}
@app.before_serving
async def cache_setup():
    print("Running cache setup")
    global guild, ban_cache

    loop = asyncio.get_event_loop()
    await bot.login(CLIENT_TOKEN)
    loop.create_task(bot.connect())

    await bot.wait_until_ready()
    guild = bot.get_guild(GUILD_ID)
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
        return await render_template("home/index.html")
    
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
    return redirect("/")

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
    user_ban_appeal_data = \
        database.banAppeals.find_one({"_id": user_ban.get("current_appeal")}) if user_ban else None

    # If unbanned and no current appeal
    if user_ban and ban_entry is None:
        return await render_template("profile/index.html", user_data=user_data, user_ban_appeal_data=user_ban_appeal_data)
    
    if ban_entry is None:
        return """
            <h1>You are not banned 🤦‍♀️</h1>
            <a href="/logout">Logout</a>
        """

    if not user_ban:
        database.bans.insert_one({
            "user_id": user_id,
            "username": f"{user_data['username']}#{user_data['discriminator']}",
            "appeals": [],
            "current_appeal": None,
        })

    reappeal_time = user_ban_appeal_data.get("reappeal_time", None) if user_ban_appeal_data else None
    if reappeal_time:
        reappeal_time = reappeal_time - time.time()

    # If reappeal time is / has reached 0 and ban is not permanent, then user can reappeal
    if user_ban_appeal_data and user_ban_appeal_data.get("reappeal_time", None):

        # Check if duration has passed
        if reappeal_time <= 0 and not user_ban_appeal_data["permanent"]:
            database.bans.find_one_and_update(
                { "user_id": user_id },
                { "$set": { "current_appeal": None } }
            )

            user_ban_appeal_data = None

        if reappeal_time > 0:
            # Get remaining time in readable format
            reappeal_time = datetime.timedelta(seconds=reappeal_time)
            reappeal_time = str(reappeal_time).split(".")[0]

    return await render_template("profile/index.html", user_data=user_data, user_ban_appeal_data=user_ban_appeal_data, reappeal_time=reappeal_time)

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

    user_ban_appeal = database.bans.find_one_and_update(
        { "user_id": user_id },
        { "$set": {
            "current_appeal": ban_appeal.inserted_id,
            "appeals": user_ban_appeal["appeals"] + [ban_appeal.inserted_id]
        }
    })

    appeal_channel = bot.get_channel(BAN_APPEAL_CHANNEL_ID)
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

    if len(user_ban_appeal["appeals"]) > 1:
        await thread.send(
            f"⚠️ This user has appealed {len(user_ban_appeal['appeals'])} time(s) before."
        )

    return redirect("/profile")

@app.route("/appeal-status")
async def appeal():
    # Check if request does not have event stream headers
    if "text/event-stream" not in request.accept_mimetypes:
        abort(400)

    user_data = session.get("user_data")
    if user_data is None:
        abort(400)
    
    async def get_ban_status():
        await asyncio.sleep(30)
        user_ban = database.bans.find_one({"user_id": int(user_data["id"])})
        if user_ban is None:
            abort(400)
        
        user_ban_appeal = database.banAppeals.find_one({"_id": user_ban["current_appeal"]})
        if user_ban_appeal is None:
            abort(400)
        
        yield f"""data: {{ "status": "{user_ban_appeal["status"]}" }}\n\n"""

    response = await make_response(
        get_ban_status(),
        {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Transfer-Encoding': 'chunked',
        }
    )
    response.timeout = None
    return response
