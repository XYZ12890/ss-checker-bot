import discord
from discord.ext import commands
import pytesseract
from PIL import Image
import aiohttp
import io
import os
from flask import Flask
from threading import Thread
import pytesseract
try:
    print("Tesseract version:", pytesseract.get_tesseract_version())
except Exception as e:
    print("Tesseract is NOT installed or not found in PATH:", e)
    

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Configuration
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1395273290703966320
VERIFIED_ROLE_NAME = "Verified"
REGISTER_CHANNEL_ID = 1395257235881328681
ALLOWED_KEYWORDS = ["sent", "SBI", "YBL", "UPI", "successfully", "debited", "credited", "payment", "to", "rs", "via"]

used_images = set()
user_warnings = {}

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.channel.id != CHANNEL_ID or not message.attachments or message.author.bot:
        return

    attachment_url = message.attachments[0].url

    if attachment_url in used_images:
        await message.reply("❌ This screenshot has already been used. You are allowed **one retry**.")
        if message.author.id in user_warnings:
            await message.reply("⚠️ Multiple invalid attempts! You are now blocked from verifying again.")
            await message.delete()
        else:
            user_warnings[message.author.id] = True
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment_url) as resp:
                if resp.status == 200:
                    image_data = await resp.read()
                    image = Image.open(io.BytesIO(image_data))
                    text = pytesseract.image_to_string(image).lower()

                    print("OCR TEXT:\n", text)

                    if any(keyword in text for keyword in ALLOWED_KEYWORDS):
                        used_images.add(attachment_url)
                        role = discord.utils.get(message.guild.roles, name=VERIFIED_ROLE_NAME)
                        if role:
                            await message.author.add_roles(role)
                        await message.add_reaction("✅")
                        await message.reply(f"✅ Your payment is verified!\n➡️ Now register your team in <#{REGISTER_CHANNEL_ID}>")
                    else:
                        await message.reply("❌ This does not appear to be a valid payment screenshot.\n⚠️ Please send a valid UPI/QR payment screenshot. One retry is allowed.")
                        if message.author.id in user_warnings:
                            await message.delete()
                        else:
                            user_warnings[message.author.id] = True

                else:
                    await message.reply("❌ Failed to download image. Please try again.")

    except Exception as e:
        print(f"Error: {e}")
        await message.reply("❌ An error occurred while processing your screenshot.")

    await bot.process_commands(message)

keep_alive()
bot.run(TOKEN)
