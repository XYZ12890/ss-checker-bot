import discord
import asyncio
import io
from PIL import Image
import pytesseract
import random

# --- CONFIG ---
CAPTCHA_TIMEOUT = 60  # seconds
VERIFIED_ROLE_NAME = "Verified"     # Change as needed for your server
VERIFIED_LIST_CHANNEL_ID = 1234567890  # Replace with your verified-list channel id


intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = discord.Client(intents=intents)

# Dummy DB function
def db_connect():
    import sqlite3
    return sqlite3.connect("verified_users.db")

def is_payment_screenshot(text):
    # Simple OCR keyword check (customize for your needs)
    return "payment" in text.lower() or "success" in text.lower() or "transaction" in text.lower()

def extract_ign_uid(content):
    try:
        parts = content.split()
        ign = None
        uid = None
        for i, p in enumerate(parts):
            if p.lower() == "ign:" and i + 1 < len(parts):
                ign = parts[i + 1]
            if p.lower() == "uid:" and i + 1 < len(parts):
                uid = parts[i + 1]
        return ign, uid
    except Exception:
        return None, None

def random_captcha():
    # Generate a random 5-character alphanumeric captcha
    return ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=5))

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
            await channel.send(f"{user.mention}, please enable Direct Messages (DMs) from server members so the bot can send you the verification captcha.")
        return False
    except asyncio.TimeoutError:
        try:
            await dm.send("Captcha timed out. Please start verification again.")
        except Exception:
            pass
        return False

async def start_verification(message, image_bytes):
    discord_id = str(message.author.id)
    image_stream = io.BytesIO(image_bytes)
    img = Image.open(image_stream)
    text = pytesseract.image_to_string(img)
    if not is_payment_screenshot(text):
        await message.reply(
            "❌ This does not appear to be a valid payment screenshot. Make sure your screenshot contains a payment confirmation."
        )
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
            c.execute("CREATE TABLE IF NOT EXISTS verified_users (discord_id TEXT PRIMARY KEY, ign TEXT, uid TEXT, payment_verified INTEGER)")
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
            # Audit log (optional function, can be implemented as needed)
            # await send_audit_log(guild, embed)
        except asyncio.TimeoutError:
            await dm.send("Timeout! Please start verification again.")
    except discord.Forbidden:
        await message.channel.send(
            f"{message.author.mention}, please enable Direct Messages (DMs) from server members so the bot can complete your verification."
        )

async def update_verified_list_channel(guild):
    # Update a status channel for all verified users (dummy implementation)
    try:
        channel = guild.get_channel(VERIFIED_LIST_CHANNEL_ID)
        if not channel:
            return
        conn = db_connect()
        c = conn.cursor()
        c.execute("SELECT ign, uid FROM verified_users WHERE payment_verified=1")
        verified = c.fetchall()
        conn.close()
        lines = [f"{ign} ({uid})" for ign, uid in verified]
        content = "Verified users:\n" + "\n".join(lines) if lines else "No verified users yet."
        async for msg in channel.history(limit=5):
            await msg.delete()
        await channel.send(content)
    except Exception as e:
        print("Error updating verified list channel:", e)

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    # Example usage: user sends `!verify` with attachment (payment screenshot)
    if message.content.startswith("!verify"):
        if message.attachments:
            try:
                image_bytes = await message.attachments[0].read()
                await start_verification(message, image_bytes)
            except Exception as e:
                await message.reply(f"Error processing screenshot: {e}")
        else:
            await message.reply("Please attach your payment screenshot with the !verify command.")

# Start the bot
bot.run("DISCORD_TOKEN")
