import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import asyncio

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
print(f"Token loaded: {token}")
print(f"Token length: {len(token) if token else 'None'}")

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Dictionary to store welcome message IDs: {member_id: message_id}
welcome_messages = {}

# Dictionary to store request-to-join message IDs: {member_id: message_id}
request_messages = {}

# List of valid classes
VALID_CLASSES = ["Warrior", "Mage", "Healer", "Warlock", "Ranger", "Tank", "Assassin"]  # Customize as needed

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')

@bot.event
async def on_member_join(member):
    print(f'{member} has joined the server.')
    
    # Send a welcome message to the enlistment channel
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
            # Store the message ID so we can delete it later
            welcome_messages[member.id] = msg.id
        except Exception as e:
            print(f"Could not send message to enlistment channel: {e}")
    else:
        print("Enlistment channel not found")

@bot.event
async def on_member_update(before, after):
    # Check if member got a new role
    new_roles = set(after.roles) - set(before.roles)
    
    if new_roles and after.id in welcome_messages:
        # Check if any of the new roles are "Member Pending" or "Visitor"
        role_names = [role.name for role in new_roles]
        if any(role_name in ["Member Pending", "Visitor"] for role_name in role_names):
            try:
                # Find and delete the message from the enlistment channel
                enlistment_channel = discord.utils.get(after.guild.channels, name='enlistment')
                if enlistment_channel:
                    try:
                        msg = await enlistment_channel.fetch_message(welcome_messages[after.id])
                        await msg.delete()
                        print(f"Deleted welcome message for {after.mention}")
                    except discord.NotFound:
                        print(f"Message for {after.mention} not found")
                    finally:
                        del welcome_messages[after.id]
            except Exception as e:
                print(f"Could not delete message: {e}")
            
            # Remove the "Pending" role
            pending_role = discord.utils.get(after.guild.roles, name="Pending")
            if pending_role and pending_role in after.roles:
                try:
                    await after.remove_roles(pending_role)
                    print(f"Removed pending role from {after.mention}")
                except Exception as e:
                    print(f"Could not remove pending role: {e}")
            
            # If they chose "Member Pending", send them a form request message
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
                        # Store the message ID so we can delete it after registration
                        request_messages[after.id] = msg.id
                    except Exception as e:
                        print(f"Could not send message to request-to-join: {e}")

@bot.command(name='register')
async def register(ctx):
    """Registration command for members to fill out their info in the channel"""
    
    # Don't respond to bot accounts
    if ctx.author.bot:
        return
    
    user = ctx.author
    messages_to_delete = [ctx.message]  # Include the command message itself
    
    try:
        # Ask for Username
        msg = await ctx.send(f"{user.mention}, welcome to the registration form! Let's get you set up.\n\nWhat is your **Username**?")
        messages_to_delete.append(msg)
        
        def check(m):
            return m.author == user and m.channel == ctx.channel
        
        # Get username
        username_msg = await bot.wait_for('message', check=check, timeout=300)
        username = username_msg.content
        messages_to_delete.append(username_msg)
        
        # Ask for Class
        class_list = ", ".join(VALID_CLASSES)
        msg = await ctx.send(f"{user.mention}, what is your **Class**? (Options: {class_list})\n*Note: Class names are case-sensitive!*")
        messages_to_delete.append(msg)
        
        class_msg = await bot.wait_for('message', check=check, timeout=300)
        player_class = class_msg.content.strip()
        messages_to_delete.append(class_msg)
        
        # Validate class
        if player_class not in VALID_CLASSES:
            error_msg = await ctx.send(f"{user.mention} ❌ Invalid class! Valid options are: {class_list}")
            messages_to_delete.append(error_msg)
            # Delete all messages
            for m in messages_to_delete:
                try:
                    await m.delete()
                except:
                    pass
            return
        
        # Ask for Level
        msg = await ctx.send(f"{user.mention}, what is your **Level**? (Must be 10 or higher)")
        messages_to_delete.append(msg)
        
        level_msg = await bot.wait_for('message', check=check, timeout=300)
        messages_to_delete.append(level_msg)
        
        try:
            level = int(level_msg.content.strip())
        except ValueError:
            error_msg = await ctx.send(f"{user.mention} ❌ Level must be a number!")
            messages_to_delete.append(error_msg)
            # Delete all messages
            for m in messages_to_delete:
                try:
                    await m.delete()
                except:
                    pass
            return
        
        # Check if level is >= 10
        if level < 10:
            error_msg = await ctx.send(f"{user.mention} ❌ Your level ({level}) is below the minimum requirement of 10. You cannot register yet.")
            messages_to_delete.append(error_msg)
            # Delete all messages
            for m in messages_to_delete:
                try:
                    await m.delete()
                except:
                    pass
            return
        
        # All validation passed! Now process the registration
        guild = ctx.guild
        
        # 1. Rename the user
        try:
            await user.edit(nick=username)
            print(f"Renamed {user} to {username}")
        except Exception as e:
            error_msg = await ctx.send(f"{user.mention} ⚠️ Could not rename you: {e}")
            messages_to_delete.append(error_msg)
        
        # 2. Get the class role and assign it
        class_role = discord.utils.get(guild.roles, name=player_class)
        if class_role:
            try:
                await user.add_roles(class_role)
                print(f"Added {player_class} role to {user}")
            except Exception as e:
                error_msg = await ctx.send(f"{user.mention} ⚠️ Could not assign {player_class} role: {e}")
                messages_to_delete.append(error_msg)
        else:
            available_roles = [r.name for r in guild.roles if not r.name.startswith('@')]
            error_msg = await ctx.send(f"{user.mention} ⚠️ {player_class} role not found in the server")
            messages_to_delete.append(error_msg)
        
        # 3. Add the "Member" role and rank role
        member_role = discord.utils.get(guild.roles, name="Member")
        rank_role = discord.utils.get(guild.roles, name="ㅤㅤㅤㅤㅤㅤRankㅤㅤㅤㅤㅤㅤㅤ")
        
        if member_role:
            try:
                await user.add_roles(member_role)
                print(f"Added member role to {user}")
            except Exception as e:
                error_msg = await ctx.send(f"{user.mention} ⚠️ Could not assign member role: {e}")
                messages_to_delete.append(error_msg)
                print(f"Error adding member role: {e}")
        else:
            available_roles = [r.name for r in guild.roles if not r.name.startswith('@')]
            error_msg = await ctx.send(f"{user.mention} ⚠️ Member role not found! Available roles: {', '.join(available_roles[:10])}")
            messages_to_delete.append(error_msg)
        
        # Add the rank role
        if rank_role:
            try:
                await user.add_roles(rank_role)
                print(f"Added rank role to {user}")
            except Exception as e:
                error_msg = await ctx.send(f"{user.mention} ⚠️ Could not assign rank role: {e}")
                messages_to_delete.append(error_msg)
                print(f"Error adding rank role: {e}")
        else:
            print(f"Rank role not found for {user}")
        
        # 4. Remove the "member pending" role
        member_pending_role = discord.utils.get(guild.roles, name="Member Pending")
        if member_pending_role and member_pending_role in user.roles:
            try:
                await user.remove_roles(member_pending_role)
                print(f"Removed Member Pending role from {user}")
            except Exception as e:
                error_msg = await ctx.send(f"{user.mention} ⚠️ Could not remove Member Pending role: {e}")
                messages_to_delete.append(error_msg)
        
        # Delete all Q&A messages
        for m in messages_to_delete:
            try:
                await m.delete()
            except:
                pass
        
        # Send confirmation to #registrations channel
        registrations_channel = discord.utils.get(guild.channels, name='registrations')
        if registrations_channel:
            await registrations_channel.send(
                f"{user.mention} ✅ Registration complete!\n\n"
                f"**Username:** {username}\n"
                f"**Class:** {player_class}\n"
                f"**Level:** {level}\n\n"
                f"Welcome to the server!"
            )
        else:
            # If registrations channel doesn't exist, just skip sending the confirmation
            print(f"Registrations channel not found for {user}")
        
        # Delete the request-to-join message if it exists
        if user.id in request_messages:
            try:
                request_channel = discord.utils.get(guild.channels, name='request-to-join')
                if request_channel:
                    msg = await request_channel.fetch_message(request_messages[user.id])
                    await msg.delete()
                    print(f"Deleted request message for {user}")
                del request_messages[user.id]
            except discord.NotFound:
                print(f"Request message for {user} not found")
            except Exception as e:
                print(f"Could not delete request message: {e}")
        
    except asyncio.TimeoutError:
        error_msg = await ctx.send(f"{user.mention} ❌ Registration timed out. Please try again with `!register`")
        messages_to_delete.append(error_msg)
        # Delete all messages
        for m in messages_to_delete:
            try:
                await m.delete()
            except:
                pass
    except Exception as e:
        print(f"Registration error: {e}")
        error_msg = await ctx.send(f"{user.mention} ❌ An error occurred: {e}")
        messages_to_delete.append(error_msg)
        # Delete all messages
        for m in messages_to_delete:
            try:
                await m.delete()
            except:
                pass

bot.run(token, log_handler=handler, log_level=logging.DEBUG)