import discord
import asyncio
import io
from PIL import Image
import pytesseract

# ... rest of your imports and variables ...

async def captcha_challenge(user: discord.User, channel=None):
    captcha = random_captcha()
    try:
        dm = await user.create_dm()
        await dm.send(embed=discord.Embed(
            title="Captcha Challenge",
            description=f"Please type the following code to continue:\n`{captcha}`",
            color=discord.Color.blue()
        ))
        def check(m):
            return m.author.id == user.id and m.channel == dm
        msg = await bot.wait_for('message', check=check, timeout=CAPTCHA_TIMEOUT)
        if msg.content.strip() == captcha:
            await dm.send("Captcha passed! Proceeding with verification.")
            return True
        else:
            await dm.send("Incorrect captcha. Please try the process again later.")
            return False
    except discord.Forbidden:
        if channel:
            await channel.send(f"{user.mention}, please enable Direct Messages (DMs) from server members so the bot can send you the verification captcha.")
        return False
    except asyncio.TimeoutError:
        try:
            await dm.send("Captcha timed out. Please start verification again.")
        except Exception:
            pass
        return False

# --- PAYMENT SCREENSHOT HANDLING ---

async def start_verification(message, image_bytes):
    discord_id = str(message.author.id)
    # OCR
    image_stream = io.BytesIO(image_bytes)
    img = Image.open(image_stream)
    text = pytesseract.image_to_string(img)
    if not is_payment_screenshot(text):
        await message.reply("❌ This does not appear to be a valid payment screenshot. Make sure your screenshot contains a payment confirmation.")
        await message.delete()
        return

    # Captcha
    passed = await captcha_challenge(message.author, channel=message.channel)
    if not passed:
        # If captcha_challenge failed due to DM permissions, the user is already notified.
        return

    # Ask for IGN and UID in DM (privacy)
    try:
        dm = await message.author.create_dm()
        await dm.send(embed=discord.Embed(
            title="Almost Done!",
            description="Please reply with your **IGN** and **UID** in the following format:\n\n`IGN: YourName UID: YourUID`",
            color=discord.Color.green()
        ))
        def ignuid_check(m):
            return m.author.id == message.author.id and m.channel == dm
        try:
            ignuid_msg = await bot.wait_for('message', check=ignuid_check, timeout=180)
            ign, uid = extract_ign_uid(ignuid_msg.content)
            if not ign or not uid:
                await dm.send("❌ Invalid format. Please use: `IGN: YourName UID: YourUID`.")
                return
            # Save to DB
            conn = db_connect()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO verified_users (discord_id, ign, uid, payment_verified) VALUES (?, ?, ?, ?)",
                      (discord_id, ign, uid, 1))
            conn.commit()
            conn.close()
            # Give role
            guild = message.guild
            member = guild.get_member(message.author.id)
            if member:
                role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)
                if role:
                    await member.add_roles(role, reason="Payment verified")
            # Update verified list channel
            await update_verified_list_channel(guild)
            # Success DM
            await dm.send(embed=discord.Embed(
                title="✅ Verification Complete!",
                description="You are now verified and have access to the server.",
                color=discord.Color.green()
            ))
            # Audit log
            embed = discord.Embed(
                title="User Verified",
                description=f"User: {message.author.mention}\nIGN: {ign}\nUID: {uid}",
                color=discord.Color.green()
            )
            await send_audit_log(guild, embed)
        except asyncio.TimeoutError:
            await dm.send("Timeout! Please start verification again.")
    except discord.Forbidden:
        await message.channel.send(
            f"{message.author.mention}, please enable Direct Messages (DMs) from server members so the bot can complete your verification."
        )

async def update_verified_list_channel(guild):
    # Show all verified users in VERIFIED_LIST_CHANNEL_ID

# ... rest of your code ...
