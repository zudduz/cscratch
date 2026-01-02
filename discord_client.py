import datetime
import logging
import discord
from google.api_core.exceptions import AlreadyExists
from google.cloud.firestore import AsyncClient

# Import the Domain Logic
import game_engine

# --- Discord Client Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

client = discord.Client(intents=intents)

# Independent Firestore client for UI-layer Idempotency (preventing double-clicks)
firestore_client = AsyncClient(database="sandbox")

# --- Idempotency Helper ---
async def should_process_message(message_id: str) -> bool:
    """
    UI Logic: Checks if this specific Discord message event has been handled.
    """
    try:
        await firestore_client.collection("processed_messages").document(str(message_id)).create({
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "status": "processing"
        })
        return True
    except AlreadyExists:
        logging.warning(f"Prevented double-move: Message {message_id} was already processed.")
        return False
    except Exception as e:
        logging.error(f"Idempotency check failed: {e}")
        return False 

# --- Events ---
@client.event
async def on_ready():
    logging.info(f'Discord Bot Connected: We have logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # IDEMPOTENCY CHECK
    if message.content.startswith('!'):
        if not await should_process_message(message.id):
            return

    # Basic Ping
    if message.content.startswith('!ping'):
        await message.channel.send('Pong! (Hello from Cloud Run)')

    # --- COMMAND: START GAME ---
    if message.content == '!start':
        try:
            # 1. Domain: Ask Game Engine to initialize a session
            game_id = await game_engine.start_new_game(story_id="sleeping-agent")
            
            # 2. UI: Build the visual representation (Channels)
            guild = message.guild
            category = await guild.create_category(f"Game {game_id}")
            channel = await guild.create_text_channel("adventure", category=category)
            
            # 3. Domain: Report back the interface location
            # We tell the engine: "This game lives in Discord Channel X"
            await game_engine.register_interface(game_id, {
                "type": "discord",
                "guild_id": str(guild.id),
                "channel_id": str(channel.id),
                "category_id": str(category.id)
            })

            # 4. UI: Feedback
            await message.channel.send(f"🚀 **Game Started!**\nID: `{game_id}`\nLocation: {channel.mention}")
            await channel.send(f"Welcome to Game `{game_id}`! The adventure begins here...")

        except Exception as e:
            logging.error(f"Error in !start command: {e}")
            await message.channel.send(f"❌ Error starting game: {str(e)}")

    # Command: Nuke (Cleanup Tool)
    if message.content.startswith('!nuke '):
        try:
            target_name = message.content.split(' ')[1]
            guild = message.guild
            deleted_count = 0

            for channel in guild.channels:
                if target_name in channel.name:
                    await channel.delete()
                    deleted_count += 1
            
            if deleted_count > 0:
                await message.channel.send(f"☢️ Nuked {deleted_count} channels/categories matching '{target_name}'")
            else:
                await message.channel.send(f"⚠️ No channels found matching '{target_name}'")

        except Exception as e:
            logging.error(f"Error in !nuke command: {e}")
            await message.channel.send(f"❌ Error nuking: {str(e)}")
