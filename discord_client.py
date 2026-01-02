import datetime
import logging
import discord
from google.api_core.exceptions import AlreadyExists
from google.cloud.firestore import AsyncClient

# --- Discord Client Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

client = discord.Client(intents=intents)

# Independent Firestore client for Idempotency locks
firestore_client = AsyncClient(database="sandbox")

# --- Idempotency Helper ---
async def should_process_message(message_id: str) -> bool:
    """
    Atomically checks if a message has been processed using a Firestore 'create' operation.
    Returns True if we secured the lock (first time seeing message), False if it was already processed.
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

    # Command: Create Category + Channel
    if message.content.startswith('!deploy '):
        try:
            base_name = message.content.split(' ')[1]
            guild = message.guild
            
            category = await guild.create_category(f"{base_name}-zone")
            channel = await guild.create_text_channel(f"{base_name}-chat", category=category)
            
            await message.channel.send(f"✅ Deployed Zone: **{category.name}** with channel <#{channel.id}>")
        except Exception as e:
            logging.error(f"Error in !deploy command: {e}")
            await message.channel.send(f"❌ Error deploying: {str(e)}")

    # Command: Delete Category + Channel
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