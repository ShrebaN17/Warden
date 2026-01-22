import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import json
import os
from collections import defaultdict

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True  # Required - enable this in Developer Portal
intents.members = False  # Set to True if you enabled it in Developer Portal
bot = commands.Bot(command_prefix='!', intents=intents)

# Configuration
UPDATE_CHANNEL_ID = None  # Set this to your channel ID
RESET_HOUR = 0  # Hour when the day resets (24-hour format)
REMINDER_HOURS = [20, 22, 23]  # Hours to send reminders
LOG_FILE = "update_logs.json"

# Storage
daily_updates = defaultdict(dict)  # {date: {user_id: update_text}}
pending_users = set()  # Users who haven't submitted today

def load_logs():
    """Load existing logs from file"""
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_logs():
    """Save logs to file"""
    with open(LOG_FILE, 'w') as f:
        json.dump(dict(daily_updates), f, indent=2)

def get_today():
    """Get today's date as string"""
    return datetime.now().strftime("%Y-%m-%d")

@bot.event
async def on_ready():
    print(f'{bot.user} is now running!')
    global daily_updates
    daily_updates = defaultdict(dict, load_logs())
    
    if not check_updates.is_running():
        check_updates.start()
    if not send_reminders.is_running():
        send_reminders.start()

@bot.command(name='setchannel')
@commands.has_permissions(administrator=True)
async def set_channel(ctx):
    """Set the current channel as the updates channel"""
    global UPDATE_CHANNEL_ID
    UPDATE_CHANNEL_ID = ctx.channel.id
    await ctx.send(f"✅ This channel has been set as the daily updates channel!")

@bot.command(name='register')
async def register_user(ctx):
    """Register a user to receive daily update reminders"""
    pending_users.add(ctx.author.id)
    await ctx.send(f"✅ {ctx.author.mention}, you've been registered for daily updates!")

@bot.command(name='unregister')
async def unregister_user(ctx):
    """Unregister a user from daily update reminders"""
    if ctx.author.id in pending_users:
        pending_users.discard(ctx.author.id)
    await ctx.send(f"✅ {ctx.author.mention}, you've been unregistered from daily updates.")

@bot.command(name='update')
async def submit_update(ctx, *, update_text: str):
    """Submit your daily update"""
    if UPDATE_CHANNEL_ID and ctx.channel.id != UPDATE_CHANNEL_ID:
        channel = bot.get_channel(UPDATE_CHANNEL_ID)
        await ctx.send(f"⚠️ Please submit your update in {channel.mention}")
        return
    
    today = get_today()
    user_id = str(ctx.author.id)
    
    daily_updates[today][user_id] = {
        'username': str(ctx.author),
        'update': update_text,
        'timestamp': datetime.now().isoformat()
    }
    
    # Remove from pending if they were registered
    if ctx.author.id in pending_users:
        pending_users.discard(ctx.author.id)
    
    save_logs()
    await ctx.send(f"✅ Update recorded for {ctx.author.mention}! Thanks for keeping us posted.")

@bot.command(name='mystatus')
async def check_status(ctx):
    """Check if you've submitted today's update"""
    today = get_today()
    user_id = str(ctx.author.id)
    
    if today in daily_updates and user_id in daily_updates[today]:
        update_data = daily_updates[today][user_id]
        await ctx.send(f"✅ You've already submitted your update today at {update_data['timestamp'][:16]}")
    else:
        await ctx.send(f"❌ You haven't submitted your update today yet. Use `!update <your update>` to submit.")

@bot.command(name='todayupdates')
@commands.has_permissions(administrator=True)
async def today_updates(ctx):
    """View all updates submitted today"""
    today = get_today()
    
    if today not in daily_updates or not daily_updates[today]:
        await ctx.send("No updates submitted today yet.")
        return
    
    embed = discord.Embed(
        title=f"📊 Daily Updates - {today}",
        color=discord.Color.blue()
    )
    
    for user_id, data in daily_updates[today].items():
        embed.add_field(
            name=f"{data['username']}",
            value=f"{data['update']}\n*Submitted at {data['timestamp'][11:16]}*",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='history')
async def user_history(ctx, days: int = 7):
    """View your update history (default: last 7 days)"""
    user_id = str(ctx.author.id)
    
    embed = discord.Embed(
        title=f"📜 Your Update History (Last {days} days)",
        color=discord.Color.green()
    )
    
    found = False
    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        if date in daily_updates and user_id in daily_updates[date]:
            data = daily_updates[date][user_id]
            embed.add_field(
                name=date,
                value=data['update'],
                inline=False
            )
            found = True
    
    if not found:
        embed.description = "No updates found in this period."
    
    await ctx.send(embed=embed)

@tasks.loop(hours=1)
async def send_reminders():
    """Send reminders to users who haven't submitted updates"""
    current_hour = datetime.now().hour
    
    if current_hour not in REMINDER_HOURS or not UPDATE_CHANNEL_ID:
        return
    
    channel = bot.get_channel(UPDATE_CHANNEL_ID)
    if not channel:
        return
    
    today = get_today()
    users_to_remind = []
    
    for user_id in pending_users:
        if str(user_id) not in daily_updates.get(today, {}):
            users_to_remind.append(user_id)
    
    if users_to_remind:
        mentions = " ".join([f"<@{uid}>" for uid in users_to_remind])
        hours_left = 24 - current_hour
        
        if hours_left <= 2:
            urgency = "⏰ **URGENT**"
        else:
            urgency = "⏰ Reminder"
        
        await channel.send(
            f"{urgency} {mentions}\n"
            f"You have **{hours_left} hour(s)** left to submit your daily update!\n"
            f"Use `!update <your update>` to submit."
        )

@tasks.loop(hours=24)
async def check_updates():
    """Reset daily tracking at midnight"""
    now = datetime.now()
    if now.hour == RESET_HOUR:
        pending_users.clear()
        # You can add all registered users back here if you want

@send_reminders.before_loop
@check_updates.before_loop
async def before_tasks():
    await bot.wait_until_ready()

@bot.command(name='help_updates')
async def help_command(ctx):
    """Show all available commands"""
    embed = discord.Embed(
        title="📋 Daily Update Bot - Commands",
        description="Track daily team updates and stay accountable!",
        color=discord.Color.purple()
    )
    
    embed.add_field(
        name="👤 User Commands",
        value=(
            "`!register` - Register for daily update reminders\n"
            "`!unregister` - Stop receiving reminders\n"
            "`!update <text>` - Submit your daily update\n"
            "`!mystatus` - Check if you've submitted today\n"
            "`!history [days]` - View your update history"
        ),
        inline=False
    )
    
    embed.add_field(
        name="👑 Admin Commands",
        value=(
            "`!setchannel` - Set current channel for updates\n"
            "`!todayupdates` - View all today's updates"
        ),
        inline=False
    )
    
    await ctx.send(embed=embed)

# Run the bot
if __name__ == "__main__":
    TOKEN = 'YOUR_TOKEN_HERE'  # Replace with your bot token
    bot.run(TOKEN)