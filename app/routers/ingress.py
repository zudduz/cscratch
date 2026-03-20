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
    context: Dict[str, Any]
    params: Dict[str, Any] = {}

class InteractionPayload(BaseModel):
    type: str 
    custom_id: str
    guild_id: Optional[str] = None
    channel_id: str
    user_id: str
    user_name: str
    values: List[str] = []
    interaction_token: Optional[str] = None
    application_id: Optional[str] = None

class TaskPayload(BaseModel):
    operation: str
    data: Optional[Dict[str, Any]] = {}

# --- ENDPOINTS ---

@router.post("/cartridge/{cartridge_id}/game/{game_id}")
async def handle_internal_task(cartridge_id: str, game_id: str, payload: TaskPayload):
    try:
        await game_engine.engine.dispatch_task(cartridge_id, game_id, payload.model_dump())
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Task Dispatch Error for game {game_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/message")
async def handle_message(payload: MessagePayload):
    if not await persistence.db.lock_event(payload.message_id):
        return {"status": "ignored", "reason": "already_processed"}

    game_id = await persistence.db.get_game_id_by_channel_index(payload.channel_id)
    if not game_id:
        return {"status": "ignored", "reason": "unknown_channel"}

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
            await handler(payload.context, payload.params)
            return {"status": "ok"}
        except Exception as e:
            logging.error(f"Command Execution Failed ({payload.command}): {e}")
            return {"status": "error", "detail": str(e)}
    
    return {"status": "ignored", "reason": "unknown_command"}

@router.post("/interaction")
async def handle_interaction(payload: InteractionPayload):
    if payload.custom_id.startswith("join_btn_"):
        game_id = payload.custom_id.replace("join_btn_", "")
        result = await game_engine.engine.join_game(game_id, payload.user_id, payload.user_name)
        
        lobby_name = presentation.format_lobby_title(
            result.get("cartridge", "Unknown"), 
            result.get("callsign", "UNK")
        )
        
        if result.get("status") == "full":
            await discord_interface.send_followup(payload.interaction_token, payload.application_id, presentation.format_lobby_full(lobby_name))
        
        elif result.get("status") == "joined":
            msg = presentation.format_player_joined(
                payload.user_name, 
                result.get("player_count"), 
                result.get("max"), 
                result.get("cost"),
                lobby_name
            )
            await discord_interface.send_message(payload.channel_id, msg)
            await discord_interface.check_and_warn_admin(payload.guild_id, payload.user_id, payload.channel_id)
            
        return {"status": result.get("status")}
    
    elif payload.custom_id.startswith("start_btn_"):
        game_id = payload.custom_id.replace("start_btn_", "")
        return await _trigger_launch(game_id, payload.user_id, payload.channel_id, payload.interaction_token, payload.application_id)
            
    elif payload.custom_id.startswith("end_delete_btn_"):
        game_id = payload.custom_id.replace("end_delete_btn_", "")
        game = await persistence.db.get_game_by_id(game_id)
        if game:
            if game.host_id != payload.user_id:
                return {"status": "denied"}
                
            lobby_name = presentation.format_lobby_title(game.story_id, game.interface.callsign or "UNK")
            await discord_interface.send_message(payload.channel_id, presentation.format_teardown(lobby_name))
            await discord_interface.cleanup_game_channels(payload.guild_id, game.interface.model_dump())
            return {"status": "deleted"}

    return {"status": "ignored"}

# --- HELPERS ---

async def _trigger_launch(game_id, user_id, channel_id, token, app_id):
    game = await persistence.db.get_game_by_id(game_id)
    lobby_name = presentation.format_lobby_title(game.story_id, game.interface.callsign or "UNK")
    
    # 1. Ephemeral Failure for Non-Hosts
    if game.host_id != user_id:
        await discord_interface.send_followup(token, app_id, presentation.ERR_NOT_HOST_START)
        return {"status": "denied"}

    # 1.5 Category Capacity Check (aux + nannies)
    needed_slots = 2 + len(game.players) 
    if not await discord_interface.check_category_capacity(game.interface.guild_id, game.interface.category_id, needed_slots):
        await discord_interface.send_followup(token, app_id, presentation.ERR_CATEGORY_FULL)
        return {"status": "denied"}

    # 2. Ephemeral Status/Balance Check for Host
    balance = await persistence.db.get_user_balance(user_id)
    
    res = await game_engine.engine.launch_match(game_id)
    
    # ALREADY STARTED (Race Condition Handling)
    if res.get("error") == "already_started":
         await discord_interface.edit_response(token, app_id, presentation.format_game_already_started(lobby_name), clear_buttons=True)
         return {"status": "ignored", "reason": "already_started"}
    
    # NOT ENOUGH MONEY
    if res.get("error") == "insufficient_funds":
         cost = res.get("cost", "Unknown")
         await discord_interface.send_followup(token, app_id, presentation.insufficient_funds(balance, cost))
         return {"status": "failed", "reason": "insufficient_funds"}

    # SYSTEM CRASHED BUT REFUNDED
    if res.get("error") == "startup_failed":
         detail = res.get("detail", "Unknown")
         await discord_interface.edit_response(token, app_id, f"**Critical Error**: Game failed to initialize.\nYour Scratch has been automatically refunded.\nDebug Info: `{detail}`", clear_buttons=True)
         return {"status": "failed", "reason": "startup_failed"}
    
    # CASE 3: SUCCESS
    if res.get('channel_ops'):
        await discord_interface.execute_channel_ops(game_id, res['channel_ops'])
        
    await game_engine.engine.dispatch_immediate_result(game_id, res)
    await game_engine.engine.trigger_post_start(game_id)
    
    # Final state: Overwrite the lobby embed with success
    callsign = game.interface.callsign or "UNK"
    cartridge = game.story_id
    await discord_interface.edit_response(token, app_id, presentation.format_game_started(callsign, cartridge), clear_buttons=True)
    
    return {"status": "launched"}