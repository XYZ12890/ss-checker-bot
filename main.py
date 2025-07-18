import discord
from discord.ext import commands
from flask import Flask
from threading import Thread
import os
import pytesseract
from PIL import Image
import requests
import cv2
import numpy as np

app = Flask(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

CHANNEL_ID = 1395273290703966320  # Screenshot verification channel
VERIFIED_ROLE_NAME = "Verified"
REGISTER_CHANNEL_ID = 1395257235881328681

used_attachments = set()

def is_payment_screenshot(image_url):
    try:
        response = requests.get(image_url, stream=True)
        img = Image.open(response.raw).convert("RGB")

        # Convert to OpenCV image
        open_cv_image = np.array(img)
        open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2BGR)

        # OCR text extraction
        text = pytesseract.image_to_string(open_cv_image).lower()

        keywords = ["upi", "pay", "payment", "qr", "rs", "paid", "amount", "to", "via", "received"]
        found_keywords = [word for word in keywords if word in text]

        return len(found_keywords) >= 3

    except Exception as e:
        print("Error during OCR:", e)
        return False

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')

@bot.event
async def on_message(message):
    if message.channel.id == CHANNEL_ID and message.attachments:
        attachment_url = message.attachments[0].url

        if attachment_url in used_attachments:
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention}, this screenshot was already used.")
            return

        # OCR check
        if is_payment_screenshot(attachment_url):
            used_attachments.add(attachment_url)
            await message.add_reaction("✅")

            role = discord.utils.get(message.guild.roles, name=VERIFIED_ROLE_NAME)
            if role:
                await message.author.add_roles(role)

            await message.reply(
                f"✅ Your payment is verified!\n➡️ Now register your team in <#{REGISTER_CHANNEL_ID}> using the format: `IGN UID Tag1 Tag2 Tag3 Tag4`"
            )
        else:
            await message.delete()
            await message.channel.send(f"🚫 {message.author.mention}, please upload a valid payment screenshot made via UPI/QR only.")

    await bot.process_commands(message)

# Flask uptime server
@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))
        
