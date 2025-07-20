import discord
import pytesseract
from PIL import Image
import io
import hashlib
import os
import threading
from flask import Flask

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

client = discord.Client(intents=intents)

# Flask heartbeat server
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

# Start Flask in a separate thread
threading.Thread(target=run_web, daemon=True).start()

# Use a file to store processed hashes for persistence
HASH_FILE = "processed_hashes.txt"

def load_processed_hashes():
    if not os.path.exists(HASH_FILE):
        return set()
    with open(HASH_FILE, "r") as f:
        return set(line.strip() for line in f.readlines())

def save_processed_hashes(processed_hashes):
    with open(HASH_FILE, "w") as f:
        for h in processed_hashes:
            f.write(f"{h}\n")

processed_hashes = load_processed_hashes()

def get_image_hash(image_bytes):
    return hashlib.sha256(image_bytes).hexdigest()

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

@client.event
async def on_message(message):
    # Ignore messages sent by the bot itself
    if message.author == client.user:
        return

    # Process only messages with attachments
    if message.attachments:
        for attachment in message.attachments:
            # Only process images (screenshots)
            if attachment.content_type and attachment.content_type.startswith('image/'):
                image_bytes = await attachment.read()
                image_hash = get_image_hash(image_bytes)

                # Reject already used screenshot
                if image_hash in processed_hashes:
                    await message.channel.send("❌ This screenshot has already been used!")
                    return

                # Add to processed hashes
                processed_hashes.add(image_hash)
                save_processed_hashes(processed_hashes)

                # Run OCR
                try:
                    image_stream = io.BytesIO(image_bytes)
                    img = Image.open(image_stream)
                    text = pytesseract.image_to_string(img)
                    await message.channel.send(f"✅ Screenshot processed!\nExtracted Text:\n```\n{text}\n```")
                except Exception as e:
                    await message.channel.send(f"⚠️ Error processing screenshot: {e}")

# Start the bot (replace 'YOUR_DISCORD_TOKEN' with your actual token or use env variable)
TOKEN = os.getenv("DISCORD_TOKEN") or "YOUR_DISCORD_TOKEN"
client.run(TOKEN)
