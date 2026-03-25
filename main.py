import discord
from discord.ext import commands, tasks
import logging
from dotenv import load_dotenv
import os
import asyncio
from datetime import time
import pytz

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
print(f"Token loaded: {token}")
print(f"Token length: {len(token) if token else 'None'}")

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Dictionaries
welcome_messages = {}        # {member_id: message_id}
request_messages = {}        # {member_id: message_id}
raid_messages = {}           # {guild_id: message}

# List of valid classes
VALID_CLASSES = ["Warrior", "Mage", "Healer", "Warlock", "Ranger", "Tank", "Assassin"]

# Timezone
VIENNA_TZ = pytz.timezone("Europe/Vienna")

# =========================
# EVENTS
# =========================

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')

    # Start raid tasks
    if not raid_signup.is_running():
        raid_signup.start()
    if not raid_start.is_running():
        raid_start.start()
    if not clear_raid_reactions.is_running():
        clear_raid_reactions.start()


@bot.event
async def on_member_join(member):
    print(f'{member} has joined the server.')

    enlistment_channel = discord.utils.get(member.guild.channels, name='enlistment')
    if enlistment_channel:
        try:
            msg = await enlistment_channel.send(
                f"Welcome {member.mention}! 👋\n\n"
                f"Please use the button system to choose how you'd like to join:\n"
                f"• **Future Member** - Join as a future member\n"
                f"• **Visitor** - Join as a visitor\n\n"
                f"Use the Dyno buttons to make your selection."
            )
            welcome_messages[member.id] = msg.id
        except Exception as e:
            print(f"Could not send message to enlistment channel: {e}")
    else:
        print("Enlistment channel not found")


@bot.event
async def on_member_update(before, after):
    new_roles = set(after.roles) - set(before.roles)

    if new_roles and after.id in welcome_messages:
        role_names = [role.name for role in new_roles]
        if any(role_name in ["Member Pending", "Visitor"] for role_name in role_names):
            try:
                enlistment_channel = discord.utils.get(after.guild.channels, name='enlistment')
                if enlistment_channel:
                    try:
                        msg = await enlistment_channel.fetch_message(welcome_messages[after.id])
                        await msg.delete()
                    except discord.NotFound:
                        pass
                    finally:
                        del welcome_messages[after.id]
            except Exception as e:
                print(f"Could not delete message: {e}")

            pending_role = discord.utils.get(after.guild.roles, name="Pending")
            if pending_role and pending_role in after.roles:
                try:
                    await after.remove_roles(pending_role)
                except Exception as e:
                    print(f"Could not remove pending role: {e}")

            if "Member Pending" in role_names:
                request_channel = discord.utils.get(after.guild.channels, name='request-to-join')
                if request_channel:
                    try:
                        msg = await request_channel.send(
                            f"{after.mention} has chosen to become a **Future Member**! 🎉\n\n"
                            f"Please use the command `!register` to complete your registration.\n"
                            f"You'll be asked for: Username, Class, and Level.\n\n"
                            f"*Note: Your level must be 10 or higher to register.*"
                        )
                        request_messages[after.id] = msg.id
                    except Exception as e:
                        print(f"Could not send message: {e}")

# =========================
# RAID SYSTEM
# =========================

@tasks.loop(time=time(hour=17, minute=0, tzinfo=VIENNA_TZ))
async def raid_signup():
    for guild in bot.guilds:
        channel = discord.utils.get(guild.channels, name='raid')
        role = discord.utils.get(guild.roles, name="Member")

        if channel and role:
            try:
                msg = await channel.send(
                    f"{role.mention} ⚔️ **Raid starting in 1 hour!**\n\n"
                    f"React below if you can join:\n"
                    f"✅ = Available\n"
                    f"❌ = Not available"
                )
                await msg.add_reaction("✅")
                await msg.add_reaction("❌")
                raid_messages[guild.id] = msg
            except Exception as e:
                print(f"Raid signup error in {guild.name}: {e}")


@tasks.loop(time=time(hour=18, minute=0, tzinfo=VIENNA_TZ))
async def raid_start():
    for guild in bot.guilds:
        channel = discord.utils.get(guild.channels, name='raid-ping')
        role = discord.utils.get(guild.roles, name="Member")

        if channel and role:
            try:
                msg = raid_messages.get(guild.id)
                if msg:
                    for reaction in msg.reactions:
                        if str(reaction.emoji) == "✅":
                            users = [user async for user in reaction.users() if not user.bot]
                            names = ", ".join([u.mention for u in users]) if users else "No one 😢"
                            await channel.send(
                                f"{role.mention} 🚨 **Raid is starting NOW!**\n\n"
                                f"✅ **Participants:** {names}"
                            )
                            break
                else:
                    await channel.send(f"{role.mention} 🚨 **Raid is starting NOW!**")
            except Exception as e:
                print(f"Raid start error in {guild.name}: {e}")


@tasks.loop(time=time(hour=18, minute=30, tzinfo=VIENNA_TZ))
async def clear_raid_reactions():
    for guild_id, msg in list(raid_messages.items()):
        try:
            await msg.clear_reactions()
        except Exception as e:
            print(f"Error clearing reactions: {e}")
        finally:
            del raid_messages[guild_id]

# =========================
# REGISTER COMMAND
# =========================

@bot.command(name='register')
async def register(ctx):
    """Registration command for members to fill out their info in the channel"""
    if ctx.author.bot:
        return

    user = ctx.author
    messages_to_delete = [ctx.message]

    try:
        msg = await ctx.send(f"{user.mention}, welcome to the registration form! Let's get you set up.\n\nWhat is your **Username**?")
        messages_to_delete.append(msg)

        def check(m):
            return m.author == user and m.channel == ctx.channel

        username_msg = await bot.wait_for('message', check=check, timeout=300)
        username = username_msg.content
        messages_to_delete.append(username_msg)

        class_list = ", ".join(VALID_CLASSES)
        msg = await ctx.send(f"{user.mention}, what is your **Class**? (Options: {class_list})\n*Note: Class names are case-sensitive!*")
        messages_to_delete.append(msg)

        class_msg = await bot.wait_for('message', check=check, timeout=300)
        player_class = class_msg.content.strip()
        messages_to_delete.append(class_msg)

        if player_class not in VALID_CLASSES:
            err = await ctx.send(f"{user.mention} ❌ Invalid class! Valid options: {class_list}")
            messages_to_delete.append(err)
            for m in messages_to_delete: 
                try: await m.delete() 
                except: pass
            return

        msg = await ctx.send(f"{user.mention}, what is your **Level**? (Must be 10 or higher)")
        messages_to_delete.append(msg)

        level_msg = await bot.wait_for('message', check=check, timeout=300)
        messages_to_delete.append(level_msg)

        try:
            level = int(level_msg.content.strip())
        except ValueError:
            err = await ctx.send(f"{user.mention} ❌ Level must be a number!")
            messages_to_delete.append(err)
            for m in messages_to_delete: 
                try: await m.delete() 
                except: pass
            return

        if level < 10:
            err = await ctx.send(f"{user.mention} ❌ Level {level} is below 10, cannot register.")
            messages_to_delete.append(err)
            for m in messages_to_delete: 
                try: await m.delete() 
                except: pass
            return

        guild = ctx.guild

        # 1. Rename
        try:
            await user.edit(nick=username)
        except Exception as e:
            err = await ctx.send(f"{user.mention} ⚠️ Could not rename: {e}")
            messages_to_delete.append(err)

        # 2. Add class role
        class_role = discord.utils.get(guild.roles, name=player_class)
        if class_role:
            try:
                await user.add_roles(class_role)
            except Exception as e:
                err = await ctx.send(f"{user.mention} ⚠️ Could not add {player_class} role: {e}")
                messages_to_delete.append(err)

        # 3. Add member + rank role
        member_role = discord.utils.get(guild.roles, name="Member")
        rank_role = discord.utils.get(guild.roles, name="ㅤㅤㅤㅤㅤㅤRankㅤㅤㅤㅤㅤㅤㅤ")
        if member_role:
            try: await user.add_roles(member_role)
            except: pass
        if rank_role:
            try: await user.add_roles(rank_role)
            except: pass

        # 4. Remove Member Pending
        pending_role = discord.utils.get(guild.roles, name="Member Pending")
        if pending_role and pending_role in user.roles:
            try: await user.remove_roles(pending_role)
            except: pass

        # Delete Q&A messages
        for m in messages_to_delete:
            try: await m.delete()
            except: pass

        # Confirmation message
        reg_channel = discord.utils.get(guild.channels, name='registrations')
        if reg_channel:
            await reg_channel.send(
                f"{user.mention} ✅ Registration complete!\n\n"
                f"**Username:** {username}\n"
                f"**Class:** {player_class}\n"
                f"**Level:** {level}\n\n"
                f"Welcome to the server!"
            )

        # Delete request-to-join message
        if user.id in request_messages:
            try:
                req_channel = discord.utils.get(guild.channels, name='request-to-join')
                if req_channel:
                    msg = await req_channel.fetch_message(request_messages[user.id])
                    await msg.delete()
                del request_messages[user.id]
            except: pass

    except asyncio.TimeoutError:
        err = await ctx.send(f"{user.mention} ❌ Registration timed out.")
        messages_to_delete.append(err)
        for m in messages_to_delete: 
            try: await m.delete() 
            except: pass
    except Exception as e:
        err = await ctx.send(f"{user.mention} ❌ An error occurred: {e}")
        messages_to_delete.append(err)
        for m in messages_to_delete: 
            try: await m.delete() 
            except: pass

# =========================
# RUN BOT
# =========================

bot.run(token, log_handler=handler, log_level=logging.DEBUG)