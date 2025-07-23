import discord
import pytesseract
from PIL import Image
import io
import hashlib
import os
import threading
import re
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

TARGET_CHANNEL_ID = 1395273290703966320
VERIFIED_LIST_CHANNEL_ID = 1397200894201958421  # Updated as per your request

HASH_FILE = "processed_hashes.txt"
VERIFIED_LIST_FILE = "verified_list.txt"
VERIFIED_LIST_MESSAGE_ID_FILE = "verified_list_message_id.txt"

awaiting_ign_uid = {}  # {user_id: True}

def load_processed_hashes():
    if not os.path.exists(HASH_FILE):
        return set()
    with open(HASH_FILE, "r") as f:
        return set(line.strip() for line in f.readlines())

def save_processed_hashes(processed_hashes):
    with open(HASH_FILE, "w") as f:
        for h in processed_hashes:
            f.write(f"{h}\n")

def load_verified_list():
    if not os.path.exists(VERIFIED_LIST_FILE):
        return []
    with open(VERIFIED_LIST_FILE, "r") as f:
        return [line.strip() for line in f.readlines()]

def save_verified_list(verified_list):
    with open(VERIFIED_LIST_FILE, "w") as f:
        for entry in verified_list:
            f.write(f"{entry}\n")

def load_verified_list_message_id():
    if not os.path.exists(VERIFIED_LIST_MESSAGE_ID_FILE):
        return None
    with open(VERIFIED_LIST_MESSAGE_ID_FILE, "r") as f:
        return f.read().strip()

def save_verified_list_message_id(message_id):
    with open(VERIFIED_LIST_MESSAGE_ID_FILE, "w") as f:
        f.write(str(message_id))

processed_hashes = load_processed_hashes()
verified_list = load_verified_list()

def get_image_hash(image_bytes):
    return hashlib.sha256(image_bytes).hexdigest()

def is_payment_screenshot(text):
    keywords = ["paid", "payment", "successful", "amount", "received", "transaction"]
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in keywords)

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

async def assign_verified_role(member):
    guild = member.guild
    verified_role = discord.utils.get(guild.roles, name="Verified")
    if verified_role and verified_role not in member.roles:
        try:
            await member.add_roles(verified_role, reason="Sent verified payment screenshot")
        except Exception as e:
            print(f"Error assigning Verified role: {e}")

async def update_verified_list_channel(guild, verified_list):
    channel = guild.get_channel(VERIFIED_LIST_CHANNEL_ID)
    if not channel:
        print("Verified list channel not found.")
        return
    content = "**Verified Players:**\n" + "\n".join(verified_list) if verified_list else "**Verified Players:**\nNo players verified yet."
    message_id = load_verified_list_message_id()
    message = None
    try:
        if message_id:
            try:
                message = await channel.fetch_message(int(message_id))
            except Exception:
                message = None
        if message:
            await message.edit(content=content)
        else:
            sent_message = await channel.send(content)
            save_verified_list_message_id(sent_message.id)
    except Exception as e:
        print(f"Error updating verified list channel: {e}")

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Step 1: Waiting for IGN/UID reply
    if message.author.id in awaiting_ign_uid:
        ign, uid = extract_ign_uid(message.content)
        if ign and uid:
            entry = f"IGN: {ign} | UID: {uid} | Discord: {message.author.mention}"
            if entry not in verified_list:
                verified_list.append(entry)
                save_verified_list(verified_list)
                await update_verified_list_channel(message.guild, verified_list)
            await message.reply("Thank you! Your IGN and UID have been recorded and you are fully verified.")
            del awaiting_ign_uid[message.author.id]
        else:
            await message.reply("IGN or UID not found in your message. Please reply in the format: `IGN: YourName UID: YourUID`.")
        return

    # Step 2: Main payment screenshot logic
    if message.channel.id != TARGET_CHANNEL_ID:
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

                # React instantly after verification
                await message.add_reaction("✅")
                processed_hashes.add(image_hash)
                save_processed_hashes(processed_hashes)
                await message.reply(
                    "Your payment is verified! Please reply with your IGN and UID in the format: `IGN: YourName UID: YourUID`."
                )
                # Assign Verified role
                member = None
                if isinstance(message.author, discord.Member):
                    member = message.author
                elif message.guild:
                    member = message.guild.get_member(message.author.id)
                if member:
                    await assign_verified_role(member)

                # Put user in awaiting_ign_uid state
                awaiting_ign_uid[message.author.id] = True

            except Exception as e:
                await message.channel.send(f"⚠️ Error processing screenshot: {e}")
                return

# Start the bot
TOKEN = os.getenv("DISCORD_TOKEN")
client.run(TOKEN)
