import discord
from discord.ext import commands
import pytesseract
import cv2
import numpy as np
from PIL import Image
import io
import os

# ✅ Set the path to your Tesseract executable
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"  # Change if needed

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

TARGET_CHANNEL_ID = 1395273290703966320
VERIFIED_ROLE_NAME = "Verified"
KEYWORDS = ["sent", "SBI", "YBL", "UPI", "success", "transfer", "received"]

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.channel.id != TARGET_CHANNEL_ID or message.author.bot:
        return

    if message.attachments:
        attachment = message.attachments[0]
        if any(attachment.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg"]):
            try:
                img_bytes = await attachment.read()
                np_img = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

                text = pytesseract.image_to_string(img).lower()
                print(f"OCR TEXT: {text}")

                if any(keyword in text for keyword in KEYWORDS):
                    await message.add_reaction("✅")
                    role = discord.utils.get(message.guild.roles, name=VERIFIED_ROLE_NAME)
                    if role:
                        await message.author.add_roles(role)
                        await message.channel.send(f"{message.author.mention}, payment verified ✅.")
                else:
                    await message.delete()
                    await message.author.send("❌ Invalid payment screenshot. Only original UPI payment SS allowed.")
            except Exception as e:
                print(f"Error: {e}")
                await message.channel.send("❌ Error processing image. Try again.")
    await bot.process_commands(message)

# Bot token from secret
import os
bot.run(os.getenv("DISCORD_TOKEN"))
        
