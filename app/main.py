import os
import uuid
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

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", str(uuid.uuid4()))
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "badtoken")

# 1. SETUP STRUCTURED LOGGING IMMEDIATELY
setup_logging()

nest_asyncio.apply()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the Discord Client (Gateway Mode)
    asyncio.create_task(discord_client.start(DISCORD_TOKEN))
    
    yield
    
    # --- SHUTDOWN SIGNAL RECEIVED (SIGTERM) ---
    logging.info("System: Shutdown signal received")
    
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