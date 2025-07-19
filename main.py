import discord
from discord.ext import commands
import pytesseract
import cv2
import numpy as np
import hashlib
from PIL import Image
import aiohttp
import io
import re

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Channel and role IDs
TARGET_CHANNEL_ID = 1395273290703966320  # Replace with your target channel ID
VERIFIED_ROLE_NAME = "Verified"

# Track used images
used_hashes = set()
retry_users = set()

# Broad keywords list
payment_keywords = [
    "payment", "received", "upi", "gpay", "paytm", "phonepe", "successful", "successfully",
    "credited", "debited", "sent", "transfer", "ybl", "sbi", "amount", "rs", "rupees",
    "to", "bhim", "done", "transaction", "upi transaction", "bank"
]

@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.channel.id != TARGET_CHANNEL_ID or message.author.bot:
        return

    if message.attachments:
        for attachment in message.attachments:
            try:
                # Download image
                img_bytes = await attachment.read()
                img_hash = hashlib.sha256(img_bytes).hexdigest()

                # Check if already used
                if img_hash in used_hashes:
                    await message.channel.send(f"⚠️ Image already used! {message.author.mention}")
                    return

                # Convert to OpenCV format
                img_stream = io.BytesIO(img_bytes)
                image = Image.open(img_stream).convert("RGB")
                open_cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

                # OCR
                extracted_text = pytesseract.image_to_string(open_cv_image).lower()

                # Check keywords
                if any(keyword in extracted_text for keyword in payment_keywords):
                    used_hashes.add(img_hash)

                    # Add reaction
                    await message.add_reaction("✅")

                    # Assign role
                    guild = message.guild
                    role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)
                    if role:
                        await message.author.add_roles(role)
                        await message.channel.send(f"✅ Payment verified! {message.author.mention} is now verified.")
                    else:
                        await message.channel.send("❌ Verified role not found.")

                else:
                    # Retry check
                    if message.author.id in retry_users:
                        await message.delete()
                        await message.channel.send(f"❌ {message.author.mention} invalid SS again. No more chances.")
                    else:
                        retry_users.add(message.author.id)
                        await message.channel.send(f"⚠️ {message.author.mention} invalid SS! Last chance, upload a real UPI payment screenshot.")
            except Exception as e:
                print("Error:", e)
                await message.channel.send("❌ Error processing image. Try again.")

    await bot.process_commands(message)

bot.run("DISCORD_TOKEN")
