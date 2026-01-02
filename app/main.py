import asyncio
import logging
from contextlib import asynccontextmanager

import nest_asyncio
from fastapi import FastAPI, Response, status
from google.cloud import secretmanager

# Import the isolated components
from discord_client import client as discord_client
# (We will import ai_engine later when we wire it up)

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
nest_asyncio.apply()

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

# --- FastAPI Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Launch Discord Bot
    token = get_discord_token()
    if token:
        asyncio.create_task(discord_client.start(token))
    else:
        logging.warning("Discord token not found. Bot will not start.")
    
    yield
    
    # Shutdown: Clean up
    if not discord_client.is_closed():
        await discord_client.close()

# --- FastAPI Setup ---
app = FastAPI(lifespan=lifespan)

@app.get("/ping")
async def ping(response: Response):
    """
    Health Check:
    Returns 200 OK if connected to Discord.
    Returns 500 Error if Zombie state.
    """
    if discord_client.is_ready():
        return {"status": "ok", "discord": "connected"}
    
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return {"status": "unhealthy", "discord": "disconnected"}