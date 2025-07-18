import discord
from discord.ext import commands
import os
from flask import Flask
import threading
from PIL import Image
import pytesseract
import requests
from io import BytesIO

# Flask app for keeping bot alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run)
    t.start()

# Discord intents
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

# Bot setup
bot = commands.Bot(command_prefix="!", intents=intents)

# Config
CHANNEL_ID = 1395273290703966320  # Screenshot verification channel
REGISTER_CHANNEL_ID = 1395257235881328681
VERIFIED_ROLE_NAME = "Verified"
used_attachments = set()

# Payment detection logic
def is_payment_screenshot(image_bytes):
    try:
        image = Image.open(image_bytes).convert("L")
        image = image.resize((image.width * 2, image.height * 2))
        image = image.point(lambda x: 0 if x < 140 else 255, '1')

        text = pytesseract.image_to_string(image).lower()
        print("OCR Text:", text)  # Debug logs

        payment_keywords = ["upi", "payment", "paytm", "gpay", "google pay", "phonepe", "rs", "transaction", "successful", "qr", "amount"]
        return any(keyword in text for keyword in payment_keywords)
    except Exception as e:
        print("OCR ERROR:", e)
        return False

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')

@bot.event
async def on_message(message):
    if message.channel.id == CHANNEL_ID and message.attachments:
        attachment_url = message.attachments[0].url

        if attachment_url in used_attachments:
            await message.reply("⚠️ This screenshot has already been used.")
            return

        response = requests.get(attachment_url)
        image_bytes = BytesIO(response.content)

        if not is_payment_screenshot(image_bytes):
            await message.reply("❌ This is not a valid payment screenshot. Please upload a real UPI/QR payment proof.")
            await message.delete(delay=5)
            return

        used_attachments.add(attachment_url)
        await message.add_reaction("✅")

        role = discord.utils.get(message.guild.roles, name=VERIFIED_ROLE_NAME)
        if role:
            await message.author.add_roles(role)

        await message.reply(
            f"✅ Your payment is verified!\n➡️ Now register your team in <#{REGISTER_CHANNEL_ID}>"
        )

    await bot.process_commands(message)

# Start Flask and bot
keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))
