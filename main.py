import asyncio
import datetime
import logging
import os
from contextlib import asynccontextmanager

import discord
import nest_asyncio
from fastapi import FastAPI, Response, status
from google.api_core.exceptions import AlreadyExists
from google.cloud import secretmanager
from google.cloud.firestore import AsyncClient
from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import MessagesState, StateGraph

# Custom Imports
from firestore_saver import FirestoreSaver

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
nest_asyncio.apply()  # Allow nested event loops for Discord + FastAPI

# --- Secret Manager Helper ---
def get_discord_token():
    """Retrieves the Discord API token from Google Secret Manager."""
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = "projects/171510694317/secrets/c-scratch-discord-api/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logging.error(f"Failed to retrieve Discord token: {e}")
        return None

# --- Discord Client Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
discord_client = discord.Client(intents=intents)

# --- AI & Database Setup ---
# We initialize these here so they are ready for the Discord bot to use later
llm = ChatVertexAI(
    model="gemini-2.5-flash",
    temperature=0.7,
)

firestore_client = AsyncClient(database="sandbox")
checkpointer = FirestoreSaver(client=firestore_client, collection="conversations")

workflow = StateGraph(state_schema=MessagesState)

def call_model(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]}

workflow.add_node("model", call_model)
workflow.set_entry_point("model")

app_graph = workflow.compile(checkpointer=checkpointer)

# --- Idempotency Helper ---
async def should_process_message(message_id: str) -> bool:
    """
    Atomically checks if a message has been processed using a Firestore 'create' operation.
    Returns True if we secured the lock (first time seeing message), False if it was already processed.
    """
    try:
        # The document ID is the message ID (which is globally unique in Discord)
        # .create() fails if the document already exists. This is our atomic lock.
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
        return False # Fail safe: don't process if DB state is unknown

# --- Discord Events ---
@discord_client.event
async def on_ready():
    logging.info(f'Discord Bot Connected: We have logged in as {discord_client.user}')

@discord_client.event
async def on_message(message):
    if message.author == discord_client.user:
        return

    # IDEMPOTENCY CHECK
    # We only apply the lock to commands starting with '!' to save DB writes on regular chat
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

# --- FastAPI Lifespan (Startup/Shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    token = get_discord_token()
    if token:
        asyncio.create_task(discord_client.start(token))
    else:
        logging.warning("Discord token not found. Bot will not start.")
    
    yield
    
    # Shutdown
    if not discord_client.is_closed():
        await discord_client.close()

# --- FastAPI Setup ---
app = FastAPI(lifespan=lifespan)

# --- Endpoints ---

@app.get("/ping")
async def ping(response: Response):
    """
    Health Check:
    Returns 200 OK if the container is running AND Discord is connected.
    Returns 500 Error if the container is running but Discord is dead (Zombie state).
    """
    if discord_client.is_ready():
        return {"status": "ok", "discord": "connected"}
    
    # If we get here, the bot is not connected to Discord
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return {"status": "unhealthy", "discord": "disconnected"}
