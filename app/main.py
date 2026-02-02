import asyncio
import logging
from contextlib import asynccontextmanager

import nest_asyncio
from fastapi import FastAPI, Response, status
from google.cloud import secretmanager

from .discord_client import client as discord_client
from . import game_engine
from .state import sys as system_state
from .gcp_log import setup_logging
from . import presentation
from .dashboard import router as dashboard_router

# 1. SETUP STRUCTURED LOGGING IMMEDIATELY
setup_logging()

nest_asyncio.apply()

def get_discord_token():
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = "projects/171510694317/secrets/c-scratch-discord-api/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logging.error(f"Failed to retrieve Discord token: {e}")
        return None

@asynccontextmanager
async def lifespan(app: FastAPI):
    token = get_discord_token()
    if token:
        # Start the Discord Client (Gateway Mode)
        asyncio.create_task(discord_client.start(token))
    else:
        logging.warning("Discord token not found. Bot will not start.")
    
    yield
    
    # --- SHUTDOWN SIGNAL RECEIVED (SIGTERM) ---
    logging.info("System: Shutdown signal received. Raising shields.")
    
    # 1. Raise Gates (Stop processing new messages immediately)
    system_state.shutting_down = True
    
    # 2. Announce Death
    if not discord_client.is_closed():
        await discord_client.announce_state(presentation.SYSTEM_OFFLINE)
        
    # 3. Kill Engine Loop
    game_engine.engine.stop()
    
    # 4. Grace Period (Wait for in-flight tasks to clear)
    await asyncio.sleep(2) 
    
    # 5. Close Discord
    if not discord_client.is_closed():
        await discord_client.close()

app = FastAPI(lifespan=lifespan)
app.include_router(dashboard_router)

@app.get("/ping")
async def ping(response: Response):
    if discord_client.is_ready():
        return {"status": "ok", "discord": "connected"}
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return {"status": "unhealthy", "discord": "disconnected"}