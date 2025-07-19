import discord
from discord.ext import commands
import os
import re

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID =   1346892731917795409# Replace with your server ID (as int)
CHANNEL_ID = 1395273290703966320
ROLE_NAME = "Verified"

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

valid_keywords = ["upi", "paytm", "sent", "success", "sbi", "ybl", "gpay", "transaction", "rs", "amount"]

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.channel.id != CHANNEL_ID or message.author.bot:
        return

    if message.attachments:
        attachment = message.attachments[0]
        if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg']):
            await attachment.save("screenshot.jpg")

            # Read image content as text
            with open("screenshot.jpg", "rb") as f:
                content = f.read().decode('latin-1').lower()
                if any(keyword in content for keyword in valid_keywords):
                    await message.add_reaction("✅")
                    guild = bot.get_guild(GUILD_ID)
                    role = discord.utils.get(guild.roles, name=ROLE_NAME)
                    member = guild.get_member(message.author.id)
                    if role and member:
                        await member.add_roles(role)
                else:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention} ⚠️ Invalid screenshot. Please upload a valid payment proof with UPI details.")
    await bot.process_commands(message)
                    
