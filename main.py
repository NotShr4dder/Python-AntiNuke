import re
import json
import emoji
import random
import sqlite3
import discord
import asyncio
import unicodedata
import datetime as dt
import string as str_module
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta

################################################### Config/Bot Config ######################################################

def load_config():
    with open('config.json', 'r') as file:
        config = json.load(file)
    return config

config = load_config()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config.get('prefix'), intents=intents)
tree = bot.tree

#############################################################################################################################

######################################################## Bot Data ###########################################################

join_group = {}
month_group = {}
join_group_last_activity = {}
raid_size = {}
original_guild_name = {}

server_data = {
    "user_heat": {},
    "user_messages": {},
    "cooldown_timers": {},
    "typing_events": {}
}

logs_channel = config.get('logs_channel')


######################################################### DATABASE #############################################################

conn = sqlite3.connect('database.db')
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS protection_settings (
    guild_id INTEGER PRIMARY KEY,
    antispammessage INTEGER DEFAULT 0,
    blockemojisspam INTEGER DEFAULT 0,
    blockmentionsspam INTEGER DEFAULT 0,
    advancedjoinprotect INTEGER DEFAULT 0,
    advancedspamblocking INTEGER DEFAULT 0,
    blockchannelcreate INTEGER DEFAULT 0,
    blockchanneldelete INTEGER DEFAULT 0,
    blockinvitebot INTEGER DEFAULT 0,
    blockserverrename INTEGER DEFAULT 0,
    nowebhook INTEGER DEFAULT 0
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS whitelist_roles (
    guild_id INTEGER,
    id INTEGER,
    antispammessage BOOLEAN,
    blockemojisspam BOOLEAN,
    blockmentionsspam BOOLEAN,
    advancedjoinprotect BOOLEAN,
    advancedspamblocking BOOLEAN,
    blockchannelcreate BOOLEAN,
    blockchanneldelete BOOLEAN,
    blockinvitebot BOOLEAN,
    blockserverrename BOOLEAN,
    nowebhook BOOLEAN,
    UNIQUE(guild_id, id)
)
''')
cursor.execute('''  
CREATE TABLE IF NOT EXISTS whitelist_users (
    guild_id INTEGER,
    id INTEGER,
    antispammessage BOOLEAN,
    blockemojisspam BOOLEAN,
    blockmentionsspam BOOLEAN,
    advancedjoinprotect BOOLEAN,
    advancedspamblocking BOOLEAN,
    blockchannelcreate BOOLEAN,
    blockchanneldelete BOOLEAN,
    blockinvitebot BOOLEAN,
    blockserverrename BOOLEAN,
    nowebhook BOOLEAN,
    UNIQUE(guild_id, id)
)
''')
conn.commit()
conn.close()


def set_default_protection_settings(guild_id: int):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO protection_settings (guild_id, antispammessage, blockemojisspam, blockmentionsspam, advancedjoinprotect, 
                                     advancedspamblocking, blockchannelcreate, blockchanneldelete, blockinvitebot, blockserverrename, nowebhook)
    VALUES (?, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
    ''', (guild_id,))
    conn.commit()
    conn.close()


def check_protection_status(guild_id: int, module: str) -> bool:
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute(f'''
    SELECT {module} FROM protection_settings WHERE guild_id = ?
    ''', (guild_id,))
    result = cursor.fetchone()
    conn.close()
    
    return result is None or result[0] == 1

def get_all_protection_statuses(guild_id: int) -> dict:
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT antispammessage, blockemojisspam, blockmentionsspam, advancedjoinprotect, 
           advancedspamblocking, blockchannelcreate, blockchanneldelete, blockinvitebot, blockserverrename, nowebhook
    FROM protection_settings WHERE guild_id = ?
    ''', (guild_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        return {
            "antispammessage": result[0],
            "blockemojisspam": result[1],
            "blockmentionsspam": result[2],
            "advancedjoinprotect": result[3],
            "advancedspamblocking": result[4],
            "blockchannelcreate": result[5],
            "blockchanneldelete": result[6],
            "blockinvitebot": result[7],
            "blockserverrename": result[8],
            "nowebhook": result[9]
        }
    else:
        return {}

def checkwhitelist(guild_id, user_id, role_ids, module):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    query_user = f"SELECT {module} FROM whitelist_users WHERE guild_id = ? AND id = ?"
    cursor.execute(query_user, (guild_id, user_id))
    user_whitelist = cursor.fetchone()

    if user_whitelist and user_whitelist[0]:
        conn.close()
        return True

    for role_id in role_ids:
        query_role = f"SELECT {module} FROM whitelist_roles WHERE guild_id = ? AND id = ?"
        cursor.execute(query_role, (guild_id, role_id))
        role_whitelist = cursor.fetchone()

        if role_whitelist and role_whitelist[0]:
            conn.close()
            return True

    conn.close()
    return False

########################################################################################################################

def is_special_character(c):
    excluded_punctuation = str_module.punctuation
    
    if c in excluded_punctuation:
        return False
    
    if unicodedata.category(c) in ('So', 'Sc', 'Sk', 'Pd', 'Ps', 'Pe', 'Pi', 'Pf', 'Po'):
        return True
    
    return False

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync()
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="RizzlerOhio | DeFirestarRX"))
    if not reduce_heat.is_running():
        reduce_heat.start()

    if not check_channels.is_running():
        check_channels.start()

    if not purge_spam.is_running():
        purge_spam.start()

    if not timeout.is_running():
        timeout.start()

    if not clear_expired_lists.is_running():
        clear_expired_lists.start()

def is_within_past_month(join_date, reference_date):
    return (reference_date - timedelta(days=30)) <= join_date <= reference_date

async def ban_members(members, guild_id, delete_messages=False):
    if guild_id not in raid_size:
        raid_size[guild_id] = []
    for member in members:
        try:
            banned_users = await guild.bans()
            if any(ban_entry.user.id == member.id for ban_entry in banned_users):
                continue

            await member.ban(delete_message_days=7 if delete_messages else 0)
            print(f"Banned {member} ({member.id})")
            ban_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            raid_size[guild_id].append(f"{ban_time} - {member.id} - @{member.name}\n")
        except: pass


@tasks.loop(seconds=1)
async def reduce_heat():
    for guild_id in server_data["user_heat"]:
        for user_id in list(server_data["user_heat"][guild_id].keys()):
            if server_data["user_heat"][guild_id][user_id]['heat'] < 100:
                server_data["user_heat"][guild_id][user_id]['heat'] -= 5
                if server_data["user_heat"][guild_id][user_id]['heat'] <= 0:
                    del server_data["user_heat"][guild_id][user_id]
                    server_data["user_messages"][guild_id].pop(user_id, None)
                    server_data["cooldown_timers"][guild_id].pop(user_id, None)

@bot.event
async def on_guild_join(guild):
    owner = guild.owner
    if owner is not None:
        try:
            await owner.send(f"Hello {owner.mention}, {bot.user} will not protect the server if it is not granted permissions. Please give it Administrator privileges and move its role and place it at the top! Make sure to setup the logs and use the whitelist command! \n -# made with love")
            print(f"{bot.user} has joined {guild}")
        except:
            pass

@bot.event
async def on_member_join(member):
    guild_id = member.guild.id
    if member.bot:
        if not check_protection_status(guild_id, 'blockinvitebot'):
            return
        async for entry in member.guild.audit_logs(action=discord.AuditLogAction.bot_add):
            if entry.target.id == member.id:
                user = entry.user
                try:
                    await member.kick(reason=f"Bot added by {user.name}.")
                    await user.ban(reason=f"Added unapproved bot: {member.name}")
                except: pass
    else:
        if not check_protection_status(guild_id, 'advancedjoinprotect'):
            return
        join_date = member.created_at.date()
        current_time = datetime.now(timezone.utc)

        if guild_id not in join_group:
            join_group[guild_id] = {}
            month_group[guild_id] = []
            join_group_last_activity[guild_id] = {}

        if join_date not in join_group[guild_id]:
            join_group[guild_id][join_date] = []
            join_group_last_activity[guild_id][join_date] = current_time

        join_group[guild_id][join_date].append(member)
        join_group_last_activity[guild_id][join_date] = current_time

        if len(join_group[guild_id][join_date]) > 5:
            await ban_members(join_group[guild_id][join_date], guild_id, delete_messages=True)
            join_group[guild_id][join_date] = []

        new_list = [member]
        found_group = False

        for group in month_group[guild_id]:
            if is_within_past_month(member.created_at, group[0].created_at):
                group.extend(new_list)
                if len(group) > 5:
                    await ban_members(group, guild_id, delete_messages=True)
                    if group in month_group[guild_id]:
                        month_group[guild_id].remove(group)
                found_group = True
                break

        if not found_group:
            month_group[guild_id].append(new_list)


@tasks.loop(seconds=60)
async def clear_expired_lists():
    now = datetime.now(timezone.utc)
    expiry_duration = timedelta(minutes=5)

    for guild_id in list(join_group.keys()):
        for join_date in list(join_group[guild_id].keys()):
            if len(join_group[guild_id][join_date]) == 0:
                del join_group[guild_id][join_date]
                del join_group_last_activity[guild_id][join_date]
            elif now - join_group_last_activity[guild_id][join_date] > expiry_duration:
                del join_group[guild_id][join_date]
                del join_group_last_activity[guild_id][join_date]

        to_remove = []
        for group in month_group[guild_id]:
            if now - max(member.joined_at for member in group) > expiry_duration:
                to_remove.append(group)

        for group in to_remove:
            month_group[guild_id].remove(group)

    for guild_id, bans in raid_size.items():
        if bans:
            guild = bot.get_guild(guild_id)
            if guild:
                log_channel = discord.utils.get(guild.channels, name=logs_channel)
                
                if log_channel:
                    try:
                        await log_channel.send("**Banned Members List:**\n" + ''.join(bans))
                    except: pass

        raid_size[guild_id] = []

@bot.event
async def on_typing(channel, user, when):
    if user.bot:
        return
    
    if channel.guild is None:
        return 
    
    guild_id = channel.guild.id
    user_id = user.id

    if guild_id not in server_data["typing_events"]:
        server_data["typing_events"][guild_id] = {}

    server_data["typing_events"][guild_id][user_id] = {
        "channel_id": channel.id,
        "time": dt.datetime.now(dt.UTC)
    }

@bot.event
async def on_message(message):
    if isinstance(message.channel, discord.DMChannel):
        return
    guild_id = message.guild.id
    role_ids = [role.id for role in message.author.roles]

    if message.webhook_id and not message.author.bot: 
        if not check_protection_status(guild_id, 'nowebhook'):
            return
        if not checkwhitelist(guild_id, message.author.id, role_ids, "nowebhook"):
            channel = message.channel
            webhooks = await channel.webhooks()
            webhook_to_delete = discord.utils.get(webhooks, id=message.webhook_id)
            
            if webhook_to_delete:
                try:
                    await webhook_to_delete.delete()
                    log_channel = discord.utils.get(guild.channels, name=logs_channel)
                    
                    if log_channel:
                        await log_channel.send(f"Webhook {message.webhook_id} has been deleted.")
                except: pass
            await message.delete()
            return

    user_id = message.author.id
    bot_member = message.guild.me
    current_time = dt.datetime.now(dt.UTC)
    attachments = message.attachments
    num_attachments = len(attachments)
    if message.author.id == bot.user.id:
        return
    log_channel = discord.utils.get(message.guild.channels, name=logs_channel)

    if guild_id not in server_data["user_heat"]:
        server_data["user_heat"][guild_id] = {}
    if guild_id not in server_data["user_messages"]:
        server_data["user_messages"][guild_id] = {}
    if guild_id not in server_data["cooldown_timers"]:
        server_data["cooldown_timers"][guild_id] = {}
    if guild_id not in server_data["typing_events"]:
        server_data["typing_events"][guild_id] = {}

    async def handle_typing_event():
        if guild_id in server_data["typing_events"]:
            if user_id in server_data["typing_events"][guild_id]:
                typing_event = server_data["typing_events"][guild_id][user_id]
                time_difference = (current_time - typing_event["time"]).total_seconds()
                if time_difference >= 180 or typing_event["channel_id"] != message.channel.id:
                    try:
                        await message.author.timeout(timedelta(hours=1), reason="Inconsistent channel after typing event")
                    except: pass
                    try:
                        await message.delete()
                    except:pass
                    try:
                        await message.author.send(f"You have been timed out for 1 hour due to suspicious activity.")                        
                        if log_channel:
                            await log_channel.send(f"{message.author.mention} has been timed out for 1 hour due to suspicious activity.")
                                
                    except: pass
                try:
                    del server_data["typing_events"][guild_id][user_id]
                except: pass
            else:
                try:
                    await message.delete()
                except: pass
                try:
                    await message.author.timeout(timedelta(hours=1), reason="Suspicious activity")
                except: pass
                try:
                    await message.author.send(f"You have been timed out for 1 hour due to suspicious activity.")
                    if log_channel:
                        await log_channel.send(f"{message.author.mention} has been timed out for 1 hour due to suspicious activity.")
                except: pass

    if check_protection_status(guild_id, 'advancedspamblocking') and not message.author.bot:
        if not checkwhitelist(guild_id, message.author.id, role_ids, "advancedspamblocking"):
            content = re.sub(r'<@!?[0-9]+>', '', message.content)
            content = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', content)
            if len(content) >= 15 and not message.author.bot:
                asyncio.create_task(handle_typing_event())

    if check_protection_status(guild_id, 'blockmentionsspam') and not message.author.bot:
        if not checkwhitelist(guild_id, message.author.id, role_ids, "blockmentionsspam"):
            ping_matches = re.compile(r'<@(?:!|&)?(\d+)>').findall(message.content)
            unique_pings = set(ping_matches)
            unique_pings.discard(str(message.author.id))
            num_unique_pings = len(unique_pings)
            if num_unique_pings >= 3:
                try:
                    await message.delete()
                except: pass
                await message.author.send(f"Limit the number of mentions per message!")

    if check_protection_status(guild_id, 'blockemojisspam'):
        if not checkwhitelist(guild_id, message.author.id, role_ids, "blockemojisspam"):
            unicode_emojis = len(emoji.emoji_list(message.content))
            custom_emojis = len(re.findall(r'<a?:\w+:\d+>', message.content))
            total_emojis = unicode_emojis + custom_emojis
            if total_emojis >= random.randint(2, 5):
                try:
                    await message.delete()
                except: pass
                try:
                    await message.author.send(f"Limit the number of emojis per message!")
                except: pass
    if check_protection_status(guild_id, 'antispammessage'):
        if not checkwhitelist(guild_id, message.author.id, role_ids, "antispammessage"):
            if user_id not in server_data["user_heat"][guild_id]:
                server_data["user_heat"][guild_id][user_id] = {'heat': 0}
                server_data["user_messages"][guild_id][user_id] = {}

            special_character = any(is_special_character(c) for c in message.content)
            if re.compile(r'<@(?:!|&)?(\d+)>').findall(message.content):
                server_data["user_heat"][guild_id][user_id]['heat'] += 30
            elif re.findall(r'<a?:\w+:\d+>', message.content) or emoji.emoji_list(message.content):
                server_data["user_heat"][guild_id][user_id]['heat'] += 25
            elif special_character:
                server_data["user_heat"][guild_id][user_id]['heat'] += 40
            else:
                server_data["user_heat"][guild_id][user_id]['heat'] += 20
            if num_attachments > 0:
                server_data["user_heat"][guild_id][user_id]['heat'] += 30*num_attachments
            if server_data["user_heat"][guild_id][user_id]['heat'] > 100:
                server_data["user_heat"][guild_id][user_id]['heat'] = 100
            if message.channel.id not in server_data["user_messages"][guild_id][user_id]:
                server_data["user_messages"][guild_id][user_id][message.channel.id] = []
            server_data["user_messages"][guild_id][user_id][message.channel.id].append(message)

    await bot.process_commands(message)


@tasks.loop()
async def timeout():
    for guild_id, users in server_data["user_heat"].items():
        for user_id, data in users.items():
            if data['heat'] == 100: 
                member = discord.utils.get(bot.get_guild(guild_id).members, id=int(user_id))
                if member and not member.is_timed_out():
                    try:
                        await member.timeout(timedelta(hours=1), reason="Detected spamming")
                    except Exception as e:
                        print(f"Failed to timeout user {user_id}: {e}")

@tasks.loop(seconds=15)
async def purge_spam():
    for guild_id, users in server_data["user_heat"].items():
        user_ids = list(users.keys())
        for user_id in user_ids:
            data = users[user_id]
            if data['heat'] == 100:
                channels_to_purge = list(server_data["user_messages"][guild_id].get(user_id, {}).keys())
                for channel_id in channels_to_purge:
                    guild = bot.get_guild(guild_id)
                    channel = bot.get_channel(channel_id)
                    if channel:
                        try:
                            user = await bot.fetch_user(user_id)
                            deleted_messages = await channel.purge(
                                check=lambda m: m in server_data["user_messages"][guild_id].get(user_id, {}).get(channel_id, [])
                            )
                            try:
                                log_channel = discord.utils.get(guild.channels, name=logs_channel)
                                
                                if log_channel:
                                    await log_channel.send(f"Spam detected! {user.mention} ({len(deleted_messages)} messages deleted)")
                            except: pass
                        except Exception as e:
                            print(f"Error purging channel: {e}")
                
                server_data["user_heat"][guild_id][user_id]['heat'] = 0
                server_data["user_messages"][guild_id][user_id] = {}


async def delete_after_delay(message, delay):
    await asyncio.sleep(delay)
    await message.delete()

@bot.event
async def on_guild_update(before, after):
    guild_id = before.id

    if guild_id not in original_guild_name:
        original_guild_name[guild_id] = before.name

    if not check_protection_status(guild_id, 'blockserverrename'):
        return

    role_ids = [role.id for role in after.members]
    if checkwhitelist(guild_id, after.owner.id, role_ids, "blockserverrename"):
        return

    if before.name != after.name and after.name != original_guild_name[guild_id]:
        async for entry in after.audit_logs(action=discord.AuditLogAction.guild_update):
            if entry.before and entry.after:
                if entry.before.name != entry.after.name:
                    user_id = entry.user.id
                    break
        else:
            user_id = None

        if user_id:
            if not checkwhitelist(guild_id, user_id, role_ids, "blockserverrename"):
                await after.edit(name=original_guild_name[guild_id])
                return



@bot.event
async def on_guild_channel_create(channel):
    guild = channel.guild
    guild_id = guild.id

    if not check_protection_status(guild_id, 'blockchannelcreate'):
        return

    async for entry in guild.audit_logs(limit=100, action=discord.AuditLogAction.channel_create):
        if entry.target.id == channel.id:
            user_id = entry.user.id

            if user_id == bot.user.id:
                return

            try:
                info = await guild.fetch_member(user_id)
                role_ids = [role.id for role in info.roles]

                if checkwhitelist(guild_id, user_id, role_ids, "blockchannelcreate"):
                    return

                if info.bot:
                    await handle_quarantine(guild, user_id)
                else:
                    if guild_id not in server_data["user_heat"]:
                        server_data["user_heat"][guild_id] = {}
                    if guild_id not in server_data["user_messages"]:
                        server_data["user_messages"][guild_id] = {}
                    if guild_id not in server_data["cooldown_timers"]:
                        server_data["cooldown_timers"][guild_id] = {}

                    if user_id not in server_data["user_heat"][guild_id]:
                        server_data["user_heat"][guild_id][user_id] = {'heat': 0}
                        server_data["user_messages"][guild_id][user_id] = {}
                        server_data["cooldown_timers"][guild_id][user_id] = None

                    server_data["user_heat"][guild_id][user_id]['heat'] += 60

                    if server_data["user_heat"][guild_id][user_id]['heat'] >= 100:
                        await handle_quarantine(guild, user_id)

            except Exception as e:
                print(f"Error fetching member info: {e}")
                pass

            await channel.delete()
@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    guild_id = guild.id

    if not check_protection_status(guild_id, 'blockchanneldelete'):
        return

    async for entry in guild.audit_logs(limit=100, action=discord.AuditLogAction.channel_delete):
        if entry.target.id == channel.id:
            user_id = entry.user.id

            if user_id == bot.user.id:
                return

            try:
                info = await guild.fetch_member(user_id)
                role_ids = [role.id for role in info.roles]

                if checkwhitelist(guild_id, user_id, role_ids, "blockchanneldelete"):
                    return

                if info.bot:
                    await handle_quarantine(guild, user_id)
                else:
                    if guild_id not in server_data["user_heat"]:
                        server_data["user_heat"][guild_id] = {}
                    if guild_id not in server_data["user_messages"]:
                        server_data["user_messages"][guild_id] = {}
                    if guild_id not in server_data["cooldown_timers"]:
                        server_data["cooldown_timers"][guild_id] = {}

                    if user_id not in server_data["user_heat"][guild_id]:
                        server_data["user_heat"][guild_id][user_id] = {'heat': 0}
                        server_data["user_messages"][guild_id][user_id] = {}
                        server_data["cooldown_timers"][guild_id][user_id] = None

                    server_data["user_heat"][guild_id][user_id]['heat'] += 60

                    if server_data["user_heat"][guild_id][user_id]['heat'] >= 100:
                        await handle_quarantine(guild, user_id)

            except Exception as e:
                print(f"Error fetching member info: {e}")
                pass

            category = channel.category
            if category:
                existing_category = discord.utils.get(guild.categories, id=category.id)
                if not existing_category:
                    category = await guild.create_category(name=category.name, position=category.position)
                else:
                    category = existing_category

            if isinstance(channel, discord.TextChannel):
                new_channel = await guild.create_text_channel(
                    name=channel.name,
                    category=category,
                    position=channel.position
                )
                for role, permissions in channel.overwrites.items():
                    await new_channel.set_permissions(role, overwrite=permissions)
                
            elif isinstance(channel, discord.VoiceChannel):
                new_channel = await guild.create_voice_channel(
                    name=channel.name,
                    category=category,
                    position=channel.position
                )
                for role, permissions in channel.overwrites.items():
                    await new_channel.set_permissions(role, overwrite=permissions)


async def handle_quarantine(guild, user_id):
    user = guild.get_member(user_id)
    log_channel = discord.utils.get(guild.channels, name=logs_channel)

    if not user:
        return

    try:
        if user.bot:
            await user.ban(reason="Antinuker")
            if log_channel:
                await log_channel.send(f"Bot {user.mention} has been banned")
        else:
            quarantine_role = discord.utils.get(guild.roles, name="Quarantine")

            for role in user.roles:
                if role != guild.default_role:
                    try:
                        await user.remove_roles(role)
                    except: pass

            try:
                await user.add_roles(quarantine_role)
                server_data["user_heat"][guild.id][user_id]['heat'] = 0
                if log_channel:
                    await log_channel.send(f"{user.mention} has been Quarantined")
            except: pass
    except: pass

@tasks.loop(seconds=120)
async def check_channels():
    for guild in bot.guilds:
        quarantine_role = discord.utils.get(guild.roles, name="Quarantine")
        if quarantine_role is None:
            try:
                quarantine_role = await guild.create_role(name="Quarantine")
            except: pass
        for channel in guild.channels:
            if isinstance(channel, discord.TextChannel) or isinstance(channel, discord.VoiceChannel) or isinstance(channel, discord.ForumChannel):
                try:
                    permissions = channel.overwrites_for(quarantine_role)
                    if permissions.view_channel is None or permissions.view_channel:
                        await channel.set_permissions(quarantine_role, view_channel=False)
                except: pass

@tree.command(name="protect", description="disable/enable protect")
@app_commands.choices(module=[
    app_commands.Choice(name="Anti spam message", value="antispammessage"),
    app_commands.Choice(name="Block emojis spam", value="blockemojisspam"),
    app_commands.Choice(name="Block mentions spam", value="blockmentionsspam"),
    app_commands.Choice(name="Advanced join protect", value="advancedjoinprotect"),
    app_commands.Choice(name="Advanced spam blocking", value="advancedspamblocking"),
    app_commands.Choice(name="Block channel create", value="blockchannelcreate"),
    app_commands.Choice(name="Block channel delete", value="blockchanneldelete"),
    app_commands.Choice(name="Block invite bot", value="blockinvitebot"),
    app_commands.Choice(name="Block server rename", value="blockserverrename"),
    app_commands.Choice(name="No webhook", value="nowebhook")
])

@app_commands.choices(event=[
    app_commands.Choice(name="Enable", value="enable"),
    app_commands.Choice(name="Disable", value="disable")
])

async def protect(interaction: discord.Interaction, module: str, event: str):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
        return
    guild_id = interaction.guild.id
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute('''
    INSERT OR IGNORE INTO protection_settings (guild_id, antispammessage, blockemojisspam, blockmentionsspam, advancedjoinprotect, 
                                             advancedspamblocking, blockchannelcreate, blockchanneldelete, blockinvitebot, blockserverrename, nowebhook)
    VALUES (?, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
    ''', (guild_id,))
    
    if event == "disable":
        cursor.execute(f'''
        UPDATE protection_settings
        SET {module} = 0
        WHERE guild_id = ?
        ''', (guild_id,))
        await interaction.response.send_message(f"Protection mode `{module}` has been turned off.", ephemeral=True)
    elif event == "enable":
        cursor.execute(f'''
        UPDATE protection_settings
        SET {module} = 1
        WHERE guild_id = ?
        ''', (guild_id,))
        await interaction.response.send_message(f"Protection mode `{module}` is enabled.", ephemeral=True)
    else:
        await interaction.response.send_message("Invalid selection.", ephemeral=True)
    
    conn.commit()
    conn.close()
@tree.command(name="status", description="check protect status")
async def status(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
        return
    guild_id = interaction.guild.id
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    statuses = get_all_protection_statuses(guild_id)

    if not statuses:
        set_default_protection_settings(guild_id)
        statuses = get_all_protection_statuses(guild_id)

    status_messages = [
        f"Anti spam message: {'enabled' if statuses['antispammessage'] else 'disabled'}",
        f"Block emojis spam: {'enabled' if statuses['blockemojisspam'] else 'disabled'}",
        f"Block mentions spam: {'enabled' if statuses['blockmentionsspam'] else 'disabled'}",
        f"Advanced join protect: {'enabled' if statuses['advancedjoinprotect'] else 'disabled'}",
        f"Advanced spam blocking: {'enabled' if statuses['advancedspamblocking'] else 'disabled'}",
        f"Block channel create: {'enabled' if statuses['blockchannelcreate'] else 'disabled'}",
        f"Block channel delete: {'enabled' if statuses['blockchanneldelete'] else 'disabled'}",
        f"Block invite bot: {'enabled' if statuses['blockinvitebot'] else 'disabled'}",
        f"Block server rename: {'enabled' if statuses['blockserverrename'] else 'disabled'}",
        f"No webhook: {'enabled' if statuses['nowebhook'] else 'disabled'}"
    ]

    status_message = "\n".join(status_messages)
    await interaction.response.send_message(f"Protection modes status:\n{status_message}", ephemeral=True)

@bot.tree.command(name="whitelist_role", description="Add role to whitelist")
@app_commands.choices(module=[
    app_commands.Choice(name="Anti spam message", value="antispammessage"),
    app_commands.Choice(name="Block emojis spam", value="blockemojisspam"),
    app_commands.Choice(name="Block mentions spam", value="blockmentionsspam"),
    app_commands.Choice(name="Advanced join protect", value="advancedjoinprotect"),
    app_commands.Choice(name="Advanced spam blocking", value="advancedspamblocking"),
    app_commands.Choice(name="Block channel create", value="blockchannelcreate"),
    app_commands.Choice(name="Block channel delete", value="blockchanneldelete"),
    app_commands.Choice(name="Block invite bot", value="blockinvitebot"),
    app_commands.Choice(name="Block server rename", value="blockserverrename"),
    app_commands.Choice(name="No webhook", value="nowebhook")
])
@app_commands.describe(role="Role")
async def whitelist_role(interaction: discord.Interaction, module: app_commands.Choice[str], role: discord.Role):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
        return

    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    guild_id = interaction.guild.id
    role_id = role.id

    query = f'''
    INSERT INTO whitelist_roles (guild_id, id, {module.value})
    VALUES (?, ?, ?)
    ON CONFLICT(guild_id, id) DO UPDATE SET {module.value} = excluded.{module.value}
    '''
    try:
        cursor.execute(query, (guild_id, role_id, True))
        conn.commit()
        await interaction.response.send_message(
            f"Successfully whitelisted role `{role.name}` for `{module.name}`!", ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
    finally:
        conn.close()



@bot.tree.command(name="whitelist_user", description="Add user to whitelist")
@app_commands.choices(module=[
    app_commands.Choice(name="Anti spam message", value="antispammessage"),
    app_commands.Choice(name="Block emojis spam", value="blockemojisspam"),
    app_commands.Choice(name="Block mentions spam", value="blockmentionsspam"),
    app_commands.Choice(name="Advanced join protect", value="advancedjoinprotect"),
    app_commands.Choice(name="Advanced spam blocking", value="advancedspamblocking"),
    app_commands.Choice(name="Block channel create", value="blockchannelcreate"),
    app_commands.Choice(name="Block channel delete", value="blockchanneldelete"),
    app_commands.Choice(name="Block invite bot", value="blockinvitebot"),
    app_commands.Choice(name="Block server rename", value="blockserverrename"),
    app_commands.Choice(name="No webhook", value="nowebhook")
])
@app_commands.describe(user="User")
async def whitelist_user(interaction: discord.Interaction, module: app_commands.Choice[str], user: discord.User):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
        return

    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    guild_id = interaction.guild.id
    user_id = user.id

    query = f'''
    INSERT INTO whitelist_users (guild_id, id, {module.value})
    VALUES (?, ?, ?)
    ON CONFLICT(guild_id, id) DO UPDATE SET {module.value} = excluded.{module.value}
    '''
    try:
        cursor.execute(query, (guild_id, user_id, True))
        conn.commit()
        await interaction.response.send_message(
            f"Successfully whitelisted user `{user.name}` for `{module.name}`!", ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
    finally:
        conn.close()


@bot.tree.command(name="remove_whitelist_role", description="Remove role from whitelist")
@app_commands.describe(role="Role")
async def remove_whitelist_role(interaction: discord.Interaction, role: discord.Role):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
        return

    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    guild_id = interaction.guild.id
    role_id = role.id

    query = '''
    DELETE FROM whitelist_roles
    WHERE guild_id = ? AND id = ?
    '''
    try:
        cursor.execute(query, (guild_id, role_id))
        conn.commit()
        await interaction.response.send_message(
            f"Successfully removed role `{role.name}` from the whitelist!", ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
    finally:
        conn.close()

@bot.tree.command(name="remove_whitelist_user", description="Remove user from whitelist")
@app_commands.describe(user="User")
async def remove_whitelist_user(interaction: discord.Interaction, user: discord.User):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
        return

    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    guild_id = interaction.guild.id
    user_id = user.id

    query = '''
    DELETE FROM whitelist_users
    WHERE guild_id = ? AND id = ?
    '''
    try:
        cursor.execute(query, (guild_id, user_id))
        conn.commit()
        await interaction.response.send_message(
            f"Successfully removed user `{user.name}` from the whitelist!", ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
    finally:
        conn.close()

@bot.tree.command(name="check_whitelist", description="Check the entire whitelist for roles and users")
async def check_whitelist(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
        return

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    guild_id = interaction.guild.id

    cursor.execute('''
        SELECT id, antispammessage, blockemojisspam, blockmentionsspam, advancedjoinprotect,
               advancedspamblocking, blockchannelcreate, blockchanneldelete, blockinvitebot,
               blockserverrename, nowebhook
        FROM whitelist_roles
        WHERE guild_id = ?
    ''', (guild_id,))
    roles_whitelist = cursor.fetchall()

    cursor.execute('''
        SELECT id, antispammessage, blockemojisspam, blockmentionsspam, advancedjoinprotect,
               advancedspamblocking, blockchannelcreate, blockchanneldelete, blockinvitebot,
               blockserverrename, nowebhook
        FROM whitelist_users
        WHERE guild_id = ?
    ''', (guild_id,))
    users_whitelist = cursor.fetchall()

    if not roles_whitelist and not users_whitelist:
        await interaction.response.send_message("No roles or users are whitelisted in this server.", ephemeral=True)
        return

    whitelist_message = "**Whitelist Information:**\n\n"

    if roles_whitelist:
        whitelist_message += "**Whitelisted Roles:**\n"
        for role in roles_whitelist:
            role_id = role[0]
            settings = role[1:]
            role_name = discord.utils.get(guild.roles, id=role_id).name
            settings_display = format_settings_short(settings)
            whitelist_message += f"Role: {role_name}: {settings_display}\n"
    
    if users_whitelist:
        whitelist_message += "\n**Whitelisted Users:**\n"
        for user in users_whitelist:
            user_id = user[0]
            settings = user[1:]
            user_name = discord.utils.get(guild.members, id=user_id).name
            settings_display = format_settings_short(settings)
            whitelist_message += f"User: {user_name}: {settings_display}\n"

    await interaction.response.send_message(whitelist_message, ephemeral=True)

    conn.close()

def format_settings_short(settings):
    setting_names = [
        "Anti spam message", "Block emojis spam", "Block mentions spam", "Advanced join protect",
        "Advanced spam blocking", "Block channel create", "Block channel delete", "Block invite bot",
        "Block server rename", "No webhook", "Log messages"
    ]
    
    enabled_settings = []

    for i, setting in enumerate(settings):
        if setting:
            enabled_settings.append(setting_names[i])

    return f"({', '.join(enabled_settings)})" if enabled_settings else "(None)"



@tree.command(name="setup", description="setup logs channel")
async def setup(interaction: discord.Interaction):
    guild = interaction.guild

    if guild is None:
        await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
        return

    channel = await guild.create_text_channel(logs_channel)

    await interaction.response.send_message(f'Log channel created: {channel.mention}', ephemeral=True)

bot.run(config.get('bot_token'))
