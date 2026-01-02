import logging
import discord

from . import game_engine
from . import persistence

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    logging.info(f'Discord Bot Connected: We have logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # 1. IDEMPOTENCY
    if message.content.startswith('!'):
        if not await persistence.lock_event(message.id):
            return

    # 2. COMMANDS
    if message.content.startswith('!ping'):
        await message.channel.send('Pong! (Hello from Cloud Run)')
        return

    if message.content == '!start':
        try:
            # START HMS BUCKET
            game_id = await game_engine.start_new_game(story_id="hms-bucket")
            guild = message.guild
            category = await guild.create_category(f"Game {game_id}")
            channel = await guild.create_text_channel("bucket-deck", category=category)
            
            await game_engine.register_interface(game_id, {
                "type": "discord",
                "guild_id": str(guild.id),
                "channel_id": str(channel.id),
                "category_id": str(category.id)
            })

            await message.channel.send(f"🌊 **HMS Bucket Launched!**\nID: `{game_id}`\nLocation: {channel.mention}")
            await channel.send("**HMS Bucket**\n*You wake up to the sound of splashing water...*")
            return
        except Exception as e:
            logging.error(f"Error in !start: {e}")
            await message.channel.send(f"❌ Error: {str(e)}")
            return

    if message.content == '!end':
        try:
            game_data = await game_engine.find_game_by_channel(message.channel.id)
            if not game_data: return
            
            interface = game_data.get('interface', {})
            cat_id = int(interface.get('category_id'))
            category = message.guild.get_channel(cat_id)
            if category:
                for c in category.channels: await c.delete()
                await category.delete()
            await game_engine.end_game(game_data['id'])
            return
        except Exception as e:
            logging.error(f"Error in !end: {e}")
            return
            
    if message.content == '!info':
        # ... (Legacy info command)
        pass

    # 3. GAMEPLAY (The Brain Transplant)
    # If it's not a command, we check if it's a move in a game channel
    if not message.content.startswith('!'):
        try:
            # Check if this channel belongs to a game
            game_data = await game_engine.find_game_by_channel(message.channel.id)
            if game_data and game_data.get('status') == 'active':
                
                # Show typing indicator while thinking
                async with message.channel.typing():
                    response_text = await game_engine.process_player_input(
                        channel_id=message.channel.id,
                        user_input=message.content
                    )
                
                # Reply
                await message.channel.send(response_text)
        except Exception as e:
            logging.error(f"Gameplay Error: {e}")
