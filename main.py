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
intents.members = True  # Needed for managing roles

client = discord.Client(intents=intents)

# Flask heartbeat server
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_web, daemon=True).start()

# Restrict to this channel only
TARGET_CHANNEL_ID = 1395273290703966320
REGISTER_CHANNEL_ID = 1395257235881328681

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

def is_payment_screenshot(text):
    keywords = ["paid", "payment", "successful", "amount", "received", "transaction"]
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in keywords)

async def assign_verified_role(member):
    guild = member.guild
    verified_role = discord.utils.get(guild.roles, name="Verified")
    if verified_role and verified_role not in member.roles:
        try:
            await member.add_roles(verified_role, reason="Sent verified payment screenshot")
        except Exception as e:
            print(f"Error assigning Verified role: {e}")

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user or message.channel.id != TARGET_CHANNEL_ID:
        return

    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith('image/'):
            image_bytes = await attachment.read()
            image_hash = get_image_hash(image_bytes)

            # Check for reused screenshot
            if image_hash in processed_hashes:
                await message.delete()
                return

            try:
                image_stream = io.BytesIO(image_bytes)
                img = Image.open(image_stream)
                text = pytesseract.image_to_string(img)

                if not is_payment_screenshot(text):
                    await message.reply("Send payment screenshot, otherwise you will be get banned.")
                    await message.delete()
                    return

                # React instantly after verification, before any processing
                await message.add_reaction("✅")
                processed_hashes.add(image_hash)
                save_processed_hashes(processed_hashes)
                # Reply with instructions and mention the register channel
                await message.reply(
                    f"Your payment is verified, head to <#{REGISTER_CHANNEL_ID}> channel."
                )
                # Assign Verified role
                member = None
                if isinstance(message.author, discord.Member):
                    member = message.author
                elif message.guild:
                    member = message.guild.get_member(message.author.id)
                if member:
                    await assign_verified_role(member)

            except Exception as e:
                await message.channel.send(f"⚠️ Error processing screenshot: {e}")
                return

# Start the bot
TOKEN = os.getenv("DISCORD_TOKEN")
client.run(TOKEN)
