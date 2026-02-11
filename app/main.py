import asyncio
import logging
from contextlib import asynccontextmanager

import nest_asyncio
from fastapi import FastAPI, Response, status

from .discord_client import client as discord_client
from . import game_engine
from .state import sys as system_state
from .gcp_log import setup_logging
from . import presentation
from . import config
from .routers import dashboard
from .routers import ingress

# 1. SETUP STRUCTURED LOGGING IMMEDIATELY
setup_logging()

nest_asyncio.apply()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start REST Interface (No WebSocket)
    await discord_client.start(config.DISCORD_TOKEN)
    # Register the headless interface with the engine
    await game_engine.engine.register_interface(discord_client)
    # Start Engine Cron
    await game_engine.engine.start()
    
    yield
    
    # --- SHUTDOWN ---
    logging.info("System: Shutdown signal received.")
    system_state.shutting_down = True
    
    if token:
        await discord_client.announce_state("System Offline")
        
    game_engine.engine.stop()
    await discord_client.close()

app = FastAPI(lifespan=lifespan)
app.include_router(dashboard.router)
app.include_router(ingress.router)

@app.get("/ping")
async def ping(response: Response):
    # Check if REST interface is authenticated
    if discord_client.is_ready:
        return {"status": "ok", "mode": "headless"}
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return {"status": "unhealthy"}