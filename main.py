import discord
import pytesseract
from PIL import Image
import io
import re
import os
import cv2
import numpy as np
from keep_alive import keep_alive

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.reactions = True
intents.members = True

client = discord.Client(intents=intents)

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_CHANNEL_ID = 1395273290703966320
VERIFIED_ROLE_NAME = "Verified"

# --- KEYWORDS ---
PAYMENT_KEYWORDS = [
    "sent", "paid", "upi", "payment", "successfully",
    "sbi", "ybl", "axis", "icici", "hdfc", "transaction", "to", "₹", "rs"
]

user_attempts = {}

# --- OCR FUNCTION ---
def extract_text(image_bytes):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        return pytesseract.image_to_string(thresh)
    except Exception as e:
        print("OCR error:", e)
        return ""

# --- MESSAGE HANDLER ---
@client.event
async def on_message(message):
    if message.channel.id != TARGET_CHANNEL_ID or message.author.bot:
        return

    if not message.attachments:
        return

    for attachment in message.attachments:
        if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg']):
            image_data = await attachment.read()
            text = extract_text(image_data).lower()

            if any(keyword in text for keyword in PAYMENT_KEYWORDS):
                await message.add_reaction("✅")
                role = discord.utils.get(message.guild.roles, name=VERIFIED_ROLE_NAME)
                if role:
                    await message.author.add_roles(role)
                await message.channel.send(f"{message.author.mention}, ✅ Payment Verified!")
            else:
                uid = str(message.author.id)
                if user_attempts.get(uid, 0) >= 1:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention} ⚠️ Invalid or reused screenshot! Contact admin.")
                else:
                    user_attempts[uid] = user_attempts.get(uid, 0) + 1
                    await message.channel.send(f"{message.author.mention} ❌ Invalid screenshot detected! One last retry allowed.")

# --- ON READY ---
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

keep_alive()
client.run(TOKEN)
