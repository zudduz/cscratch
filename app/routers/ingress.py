from fastapi import APIRouter, Header, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import logging
import discord

from .. import game_engine
from .. import persistence
from .. import presentation
from .. import config
from ..discord_client import client as discord_interface
from .. import commands

async def verify_auth(x_internal_auth: str = Header(...)):
    if x_internal_auth != config.INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")

router = APIRouter(
    prefix="/ingress", 
    tags=["ingress"],
    dependencies=[Depends(verify_auth)]
)

class MessagePayload(BaseModel):
    guild_id: Optional[str] = None
    channel_id: str
    user_id: str
    user_name: str
    content: str
    message_id: str

class CommandPayload(BaseModel):
    command: str
    # Context contains user_id, channel_id, guild_id, user_name
    context: Dict[str, Any]
    # Params contains arguments like 'cartridge', 'amount', 'recipient'
    params: Dict[str, Any] = {}

class InteractionPayload(BaseModel):
    type: str 
    custom_id: str
    guild_id: Optional[str] = None
    channel_id: str
    user_id: str
    user_name: str
    values: List[str] = []

# --- ENDPOINTS ---

@router.post("/message")
async def handle_message(payload: MessagePayload):
    # 1. IDEMPOTENCY CHECK (Distributed Lock)
    if not await persistence.db.lock_event(payload.message_id):
        logging.info(f"Duplicate event ignored: {payload.message_id}")
        return {"status": "ignored", "reason": "already_processed"}

    # 2. Lookup Game ID
    game_id = await persistence.db.get_game_id_by_channel_index(payload.channel_id)
    if not game_id:
        return {"status": "ignored", "reason": "unknown_channel"}

    # 3. Dispatch to Engine
    try:
        await game_engine.engine.dispatch_input(
            channel_id=payload.channel_id,
            user_id=payload.user_id,
            user_name=payload.user_name,
            user_input=payload.content,
            game_id=game_id
        )
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Ingress Message Error: {e}")
        return {"status": "error", "detail": str(e)}

@router.post("/command")
async def handle_command(payload: CommandPayload):
    handler = commands.REGISTRY.get(payload.command)
    
    if handler:
        try:
            # Dispatch to the specific command handler defined in app/commands.py
            await handler(payload.context, payload.params)
            return {"status": "ok"}
        except Exception as e:
            logging.error(f"Command Execution Failed ({payload.command}): {e}")
            return {"status": "error", "detail": str(e)}
    
    logging.warning(f"Unknown command received: {payload.command}")
    return {"status": "ignored", "reason": "unknown_command"}

@router.post("/interaction")
async def handle_interaction(payload: InteractionPayload):
    if payload.custom_id == "join_btn":
        game_id = await persistence.db.get_game_id_by_channel_index(payload.channel_id)
        if game_id:
            result = await game_engine.engine.join_game(game_id, payload.user_id, payload.user_name)
            
            if result.get("status") == "full":
                await discord_interface.send_message(payload.channel_id, presentation.LOBBY_FULL)
            
            elif result.get("status") == "joined":
                msg = presentation.format_player_joined(
                    payload.user_name, 
                    result.get("player_count"), 
                    result.get("max"), 
                    result.get("cost")
                )
                await discord_interface.send_message(payload.channel_id, msg)
                
                # REFACTORED: Use centralized check
                await discord_interface.check_and_warn_admin(payload.guild_id, payload.user_id, payload.channel_id)

            return {"status": result.get("status")}
    
    elif payload.custom_id == "start_btn":
        game_id = await persistence.db.get_game_id_by_channel_index(payload.channel_id)
        if game_id:
            return await _trigger_launch(game_id, payload.user_id, payload.channel_id)
            
    elif payload.custom_id == "end_delete_btn":
        game_id = await persistence.db.get_game_id_by_channel_index(payload.channel_id)
        if game_id:
            game = await persistence.db.get_game_by_id(game_id)
            if game:
                if game.host_id != payload.user_id:
                    return {"status": "denied"}
                    
                await discord_interface.send_message(payload.channel_id, presentation.MSG_TEARDOWN)
                await discord_interface.cleanup_game_channels(payload.guild_id, game.interface.model_dump())
                return {"status": "deleted"}

    return {"status": "ignored"}

# --- HELPERS ---

async def _trigger_launch(game_id, user_id, channel_id):
    game = await persistence.db.get_game_by_id(game_id)
    if game.host_id != user_id:
        await discord_interface.send_message(channel_id, presentation.ERR_NOT_HOST_START)
        return {"status": "denied"}
        
    await discord_interface.send_message(channel_id, presentation.MSG_STARTING)
    
    res = await game_engine.engine.launch_match(game_id)
    
    # CASE 1: NOT ENOUGH MONEY
    if res.get("error") == "insufficient_funds":
         cost = res.get("cost", "Unknown")
         await discord_interface.send_message(channel_id, f"**Launch Failed**: Insufficient Scratch.\nRequired: {cost} Scratch.")
         return {"status": "failed", "reason": "insufficient_funds"}

    # CASE 2: SYSTEM CRASHED BUT REFUNDED
    if res.get("error") == "startup_failed":
         detail = res.get("detail", "Unknown")
         await discord_interface.send_message(channel_id, f"**Critical Error**: Game failed to initialize.\nYour Scratch has been automatically refunded.\nDebug Info: `{detail}`")
         return {"status": "failed", "reason": "startup_failed"}
    
    # CASE 3: SUCCESS
    if res.get('channel_ops'):
        await discord_interface.execute_channel_ops(game_id, res['channel_ops'])
        
    await game_engine.engine.dispatch_immediate_result(game_id, res)
    
    await game_engine.engine.trigger_post_start(game_id)
    
    return {"status": "launched"}