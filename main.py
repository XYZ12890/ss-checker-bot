import discord
import pytesseract
from PIL import Image
import io
import hashlib
import os
import threading
import re
import asyncio
import sqlite3
import random
import string
from discord.ext import commands
from flask import Flask

# --- CONFIGURATION ---

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_CHANNEL_ID = 1395273290703966320
VERIFIED_LIST_CHANNEL_ID = 1397200894201958421
VERIFIED_ROLE_NAME = "Verified"
CAPTCHA_LENGTH = 5
CAPTCHA_TIMEOUT = 90  # seconds
VERIFICATION_COOLDOWN = 300  # seconds per user

DATABASE_NAME = "verification.db"
AUDIT_LOG_CHANNEL_NAME = "verification-logs"  # Name of the log channel to auto-create

# --- BOT SETUP ---

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
AUDIT_LOG_CHANNEL_ID = None  # Will be set dynamically

# --- DATABASE SETUP ---

def db_connect():
    return sqlite3.connect(DATABASE_NAME)

def db_setup():
    conn = db_connect()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS verified_users (
                    discord_id TEXT PRIMARY KEY,
                    ign TEXT,
                    uid TEXT,
                    payment_verified INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS payment_attempts (
                    discord_id TEXT,
                    image_hash TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS cooldowns (
                    discord_id TEXT PRIMARY KEY,
                    last_attempt INTEGER
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS appeals (
                    discord_id TEXT PRIMARY KEY,
                    reason TEXT,
                    status TEXT DEFAULT "pending",
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                 )''')
    conn.commit()
    conn.close()

db_setup()

# --- FLASK HEARTBEAT ---

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_web, daemon=True).start()

# --- UTILS ---

def get_image_hash(image_bytes):
    return hashlib.sha256(image_bytes).hexdigest()

def is_payment_screenshot(text):
    keywords = ["paid", "payment", "successful", "amount", "received", "transaction", "upi", "credited", "debited"]
    return any(keyword in text.lower() for keyword in keywords)

def extract_ign_uid(content):
    ign = None
    uid = None
    ign_match = re.search(r'ign\s*[:\-]\s*([^\n\r]+)', content, re.IGNORECASE)
    uid_match = re.search(r'uid\s*[:\-]\s*(\d+)', content, re.IGNORECASE)
    if ign_match:
        ign = ign_match.group(1).strip()
    if uid_match:
        uid = uid_match.group(1).strip()
    return ign, uid

def random_captcha(length=CAPTCHA_LENGTH):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

async def send_audit_log(guild, embed):
    global AUDIT_LOG_CHANNEL_ID
    if AUDIT_LOG_CHANNEL_ID:
        channel = guild.get_channel(AUDIT_LOG_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed)

# --- COOLDOWN CHECK ---

def set_cooldown(user_id):
    conn = db_connect()
    c = conn.cursor()
    now = int(asyncio.get_event_loop().time())
    c.execute("INSERT OR REPLACE INTO cooldowns (discord_id, last_attempt) VALUES (?, ?)", (str(user_id), now))
    conn.commit()
    conn.close()

def get_cooldown(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT last_attempt FROM cooldowns WHERE discord_id = ?", (str(user_id),))
    row = c.fetchone()
    conn.close()
    if row:
        return int(row[0])
    return None

# --- CAPTCHA CHALLENGE ---  # DM fallback logic!

async def captcha_challenge(user: discord.User, channel=None):
    captcha = random_captcha()
    try:
        dm = await user.create_dm()
        await dm.send(embed=discord.Embed(
            title="Captcha Challenge",
            description=f"Please type the following code to continue:\n`{captcha}`",
            color=discord.Color.blue()
        ))
        def check(m):
            return m.author.id == user.id and m.channel == dm
        msg = await bot.wait_for('message', check=check, timeout=CAPTCHA_TIMEOUT)
        if msg.content.strip() == captcha:
            await dm.send("Captcha passed! Proceeding with verification.")
            return True
        else:
            await dm.send("Incorrect captcha. Please try the process again later.")
            return False
    except discord.Forbidden:
        if channel:
            await channel.send(f"{user.mention}, please enable your Direct Messages (DMs) from server members so the bot can send you verification steps!")
        return False
    except asyncio.TimeoutError:
        try:
            await dm.send("Captcha timed out. Please start verification again.")
        except Exception:
            pass
        return False

# --- PAYMENT SCREENSHOT HANDLING ---  # DM fallback logic!

async def start_verification(message, image_bytes):
    discord_id = str(message.author.id)
    # OCR
    image_stream = io.BytesIO(image_bytes)
    img = Image.open(image_stream)
    text = pytesseract.image_to_string(img)
    if not is_payment_screenshot(text):
        await message.reply("❌ This does not appear to be a valid payment screenshot. Make sure your screenshot contains a payment confirmation.")
        await message.delete()
        return

    # Captcha
    passed = await captcha_challenge(message.author, channel=message.channel)
    if not passed:
        return

    # Ask for IGN and UID in DM (privacy)
    try:
        dm = await message.author.create_dm()
        await dm.send(embed=discord.Embed(
            title="Almost Done!",
            description="Please reply with your **IGN** and **UID** in the following format:\n\n`IGN: YourName UID: YourUID`",
            color=discord.Color.green()
        ))
        def ignuid_check(m):
            return m.author.id == message.author.id and m.channel == dm
        try:
            ignuid_msg = await bot.wait_for('message', check=ignuid_check, timeout=180)
            ign, uid = extract_ign_uid(ignuid_msg.content)
            if not ign or not uid:
                await dm.send("❌ Invalid format. Please use: `IGN: YourName UID: YourUID`.")
                return
            # Save to DB
            conn = db_connect()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO verified_users (discord_id, ign, uid, payment_verified) VALUES (?, ?, ?, ?)",
                      (discord_id, ign, uid, 1))
            conn.commit()
            conn.close()
            # Give role
            guild = message.guild
            member = guild.get_member(message.author.id)
            if member:
                role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)
                if role:
                    await member.add_roles(role, reason="Payment verified")
            # Update verified list channel
            await update_verified_list_channel(guild)
            # Success DM
            await dm.send(embed=discord.Embed(
                title="✅ Verification Complete!",
                description="You are now verified and have access to the server.",
                color=discord.Color.green()
            ))
            # Audit log
            embed = discord.Embed(
                title="User Verified",
                description=f"User: {message.author.mention}\nIGN: {ign}\nUID: {uid}",
                color=discord.Color.green()
            )
            await send_audit_log(guild, embed)
        except asyncio.TimeoutError:
            await dm.send("Timeout! Please start verification again.")
    except discord.Forbidden:
        await message.channel.send(
            f"{message.author.mention}, please enable your Direct Messages from server members so the bot can complete your verification."
        )

async def update_verified_list_channel(guild):
    # Show all verified users in VERIFIED_LIST_CHANNEL_ID
    channel = guild.get_channel(VERIFIED_LIST_CHANNEL_ID)
    if not channel:
        return
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT ign, uid, discord_id FROM verified_users WHERE payment_verified = 1")
    rows = c.fetchall()
    conn.close()
    entries = [f"IGN: {ign} | UID: {uid} | <@{discord_id}>" for ign, uid, discord_id in rows]
    content = "**Verified Players:**\n" + "\n".join(entries) if entries else "**Verified Players:**\nNo players verified yet."
    async for msg in channel.history(limit=10):
        if msg.author == bot.user:
            await msg.edit(content=content)
            return
    await channel.send(content)

# --- LOG CHANNEL AUTO-CREATION ---

async def get_or_create_log_channel(guild, channel_name=AUDIT_LOG_CHANNEL_NAME):
    # Try to find an existing text channel with the given name
    existing = discord.utils.get(guild.text_channels, name=channel_name)
    if existing:
        return existing
    # Otherwise, create the channel
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    channel = await guild.create_text_channel(channel_name, overwrites=overwrites, reason="Created for verification logging")
    return channel

# --- SLASH COMMANDS ---

@bot.tree.command(name="status", description="Check your verification status.")
async def status(interaction: discord.Interaction):
    discord_id = str(interaction.user.id)
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT ign, uid, payment_verified FROM verified_users WHERE discord_id = ?", (discord_id,))
    row = c.fetchone()
    conn.close()
    if row:
        ign, uid, verified = row
        embed = discord.Embed(
            title="Your Verification Status",
            description=f"IGN: {ign}\nUID: {uid}\nStatus: {'✅ Verified' if verified else '❌ Not Verified'}",
            color=discord.Color.green() if verified else discord.Color.red()
        )
    else:
        embed = discord.Embed(
            title="Not Verified",
            description="You have not completed verification yet.",
            color=discord.Color.red()
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="appeal", description="Appeal your verification rejection.")
async def appeal(interaction: discord.Interaction, reason: str):
    discord_id = str(interaction.user.id)
    conn = db_connect()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO appeals (discord_id, reason, status) VALUES (?, ?, ?)", (discord_id, reason, "pending"))
    conn.commit()
    conn.close()
    embed = discord.Embed(
        title="Appeal Submitted",
        description="Your appeal has been submitted and will be reviewed by staff.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
    # Log to audit
    guild = interaction.guild
    log_embed = discord.Embed(
        title="Appeal Submitted",
        description=f"User: <@{discord_id}>\nReason: {reason}",
        color=discord.Color.orange()
    )
    await send_audit_log(guild, log_embed)

@bot.tree.command(name="export_verified", description="(Admin) Export all verified users as CSV.")
@commands.has_permissions(administrator=True)
async def export_verified(interaction: discord.Interaction):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT ign, uid, discord_id FROM verified_users WHERE payment_verified = 1")
    rows = c.fetchall()
    conn.close()
    csv_content = "IGN,UID,DiscordID\n" + "\n".join([f"{ign},{uid},{discord_id}" for ign, uid, discord_id in rows])
    file = discord.File(io.BytesIO(csv_content.encode()), filename="verified_users.csv")
    await interaction.response.send_message("Here is the export of all verified users:", file=file, ephemeral=True)

# --- PAYMENT SCREENSHOT LISTENER ---

@bot.event
async def on_ready():
    print(f'Bot logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"Slash commands synced: {len(synced)}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

    # For every guild, ensure log channel exists and cache its ID
    for guild in bot.guilds:
        log_channel = await get_or_create_log_channel(guild)
        global AUDIT_LOG_CHANNEL_ID
        AUDIT_LOG_CHANNEL_ID = log_channel.id

        # Post a ready message in the log channel (only once)
        found = False
        async for msg in log_channel.history(limit=10):
            if msg.author == bot.user and "Verification Log Channel Ready" in msg.content:
                found = True
                break
        if not found:
            await log_channel.send(embed=discord.Embed(
                title="Verification Log Channel Ready",
                description="All verification events will be logged here.",
                color=discord.Color.purple()
            ))

    # Post welcome/instruction embed in payment channel if not already present
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if channel:
        found = False
        async for msg in channel.history(limit=10):
            if msg.author == bot.user and "How to verify" in msg.content:
                found = True
                break
        if not found:
            embed = discord.Embed(
                title="How to verify",
                description=(
                    "1. Send a clear payment screenshot in this channel.\n"
                    "2. You will receive a DM to complete captcha and provide your IGN/UID for verification.\n"
                    "3. Abuse or fake screenshots will lead to a ban.\n"
                    "4. Use `/status` at any time to check your progress."
                ),
                color=discord.Color.blue()
            )
            await channel.send(embed=embed)

@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    # Listen for payment screenshots in the payment channel
    if message.channel.id == TARGET_CHANNEL_ID:
        # Cooldown check
        last = get_cooldown(message.author.id)
        now = int(asyncio.get_event_loop().time())
        if last and now - last < VERIFICATION_COOLDOWN:
            await message.reply("⏳ Please wait before trying to verify again.")
            return

        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                image_bytes = await attachment.read()
                image_hash = get_image_hash(image_bytes)
                # Check for duplicate attempts
                conn = db_connect()
                c = conn.cursor()
                c.execute("SELECT 1 FROM payment_attempts WHERE image_hash = ?", (image_hash,))
                if c.fetchone():
                    await message.reply("❌ This screenshot has already been used. If this is a mistake, contact staff.")
                    await message.delete()
                    conn.close()
                    return
                # Log attempt
                c.execute("INSERT INTO payment_attempts (discord_id, image_hash) VALUES (?, ?)", (str(message.author.id), image_hash))
                conn.commit()
                conn.close()
                set_cooldown(message.author.id)

                await start_verification(message, image_bytes)
                return

# --- BAN ON ABUSE ---

async def ban_user(guild, user, reason):
    await guild.ban(user, reason=reason, delete_message_days=1)
    embed = discord.Embed(
        title="User Banned",
        description=f"<@{user.id}> has been banned.\nReason: {reason}",
        color=discord.Color.red()
    )
    await send_audit_log(guild, embed)

# --- RUN BOT ---

bot.run(DISCORD_TOKEN)
