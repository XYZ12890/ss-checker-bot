import discord
from discord.ext import commands
import os
from flask import Flask
import threading 
app = Flask(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

CHANNEL_ID = 1395273290703966320  # replace with your screenshot channel
VERIFIED_ROLE_NAME = "Verified"
REGISTER_CHANNEL_ID = 1395257235881328681

used_attachments = set()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_message(message):
    if message.channel.id == CHANNEL_ID and message.attachments:
        if message.attachments[0].url in used_attachments:
            await message.reply("❌ This screenshot has already been used.")
            return

        used_attachments.add(message.attachments[0].url)
        await message.add_reaction("✅")

        # Assign Role
        role = discord.utils.get(message.guild.roles, name=VERIFIED_ROLE_NAME)
        if role:
            await message.author.add_roles(role)

        # Reply message
        await message.reply(
            f"✅ Your payment is verified!\n➡️ Now register your team in <#{REGISTER_CHANNEL_ID}>"
        )

    await bot.process_commands(message)
        
    app = Flask('')

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
  
