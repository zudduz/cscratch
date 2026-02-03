from fastapi import APIRouter, Header, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import logging

from .. import game_engine
from .. import persistence
from .. import presentation
from .. import config
from ..discord_client import client as discord_interface

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
    cartridge: Optional[str] = "foster-protocol"
    guild_id: str
    channel_id: str
    user_id: str
    user_name: str

class InteractionPayload(BaseModel):
    type: str 
    custom_id: str
    guild_id: Optional[str] = None
    channel_id: str
    user_id: str
    user_name: str
    values: List[str] = []

@router.post("/message")
async def handle_message(payload: MessagePayload):
    # 1. Lookup Game ID
    game_id = await persistence.db.get_game_id_by_channel_index(payload.channel_id)
    if not game_id:
        return {"status": "ignored", "reason": "unknown_channel"}

    # 2. Dispatch to Engine
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
    if payload.command == "start":
        return await _cmd_start(payload)
    elif payload.command == "end":
        return await _cmd_end(payload)
    
    return {"status": "ignored"}

@router.post("/interaction")
async def handle_interaction(payload: InteractionPayload):
    if payload.custom_id == "join_btn":
        game_id = await persistence.db.get_game_id_by_channel_index(payload.channel_id)
        if game_id:
            await game_engine.engine.join_game(game_id, payload.user_id, payload.user_name)
            await discord_interface.send_message(payload.channel_id, presentation.format_player_joined(payload.user_name))
            return {"status": "joined"}
    
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

# --- COMMAND HELPERS ---

async def _cmd_start(p: CommandPayload):
    try:
        # 1. Create Game Record
        game_id = await game_engine.engine.start_new_game(p.cartridge, p.user_id, p.user_name)
        
        # 2. Create Channels
        guild = await discord_interface.client.fetch_guild(int(p.guild_id))
        
        cat = await guild.create_category(f"Lobby {game_id}")
        chan = await guild.create_text_channel("cscratch-lobby", category=cat)
        
        # 3. Register Interface
        await game_engine.engine.register_interface_data(game_id, {
            "type": "discord",
            "guild_id": p.guild_id,
            "category_id": str(cat.id),
            "main_channel_id": str(chan.id),
            "listener_ids": [str(chan.id)]
        })
        
        # 4. Update Index
        await persistence.db.register_channel_association(str(chan.id), game_id)
        
        # 5. Send Lobby UI
        import discord
        embed = discord.Embed(
            title=presentation.format_lobby_title(p.cartridge),
            description=presentation.LOBBY_DESC,
            color=0x00ff00
        )
        
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label=presentation.BTN_JOIN, style=discord.ButtonStyle.green, custom_id="join_btn"))
        view.add_item(discord.ui.Button(label=presentation.BTN_START, style=discord.ButtonStyle.danger, custom_id="start_btn"))
        
        await chan.send(embed=embed, view=view)
        
        await discord_interface.send_message(p.channel_id, presentation.format_lobby_created_msg(chan.mention))
        
        return {"status": "ok", "game_id": game_id}
        
    except Exception as e:
        logging.error(f"Start CMD Failed: {e}")
        await discord_interface.send_message(p.channel_id, presentation.CMD_FAILED.format(error=str(e)))
        return {"status": "error"}

async def _cmd_end(p: CommandPayload):
    game = await game_engine.engine.find_game_by_channel(p.channel_id)
    if not game:
        await discord_interface.send_message(p.channel_id, presentation.ERR_NO_GAME)
        return {"status": "no_game"}
        
    if p.user_id != game.host_id:
        await discord_interface.send_message(p.channel_id, presentation.ERR_NOT_HOST)
        return {"status": "denied"}
        
    await discord_interface.send_message(p.channel_id, presentation.MSG_TEARDOWN)
    
    report = presentation.build_cost_report(game.id, game.usage_input_tokens, game.usage_output_tokens)
    await discord_interface.announce_state(report)
    
    await discord_interface.cleanup_game_channels(p.guild_id, game.interface.model_dump())
    await game_engine.engine.end_game(game.id)
    
    return {"status": "ended"}

async def _trigger_launch(game_id, user_id, channel_id):
    game = await persistence.db.get_game_by_id(game_id)
    if game.host_id != user_id:
        await discord_interface.send_message(channel_id, presentation.ERR_NOT_HOST_START)
        return {"status": "denied"}
        
    await discord_interface.send_message(channel_id, presentation.MSG_STARTING)
    
    res = await game_engine.engine.launch_match(game_id)
    
    if res.get('channel_ops'):
        await discord_interface.execute_channel_ops(game_id, res['channel_ops'])
        
    await game_engine.engine.dispatch_immediate_result(game_id, res)
    
    await game_engine.engine.trigger_post_start(game_id)
    
    return {"status": "launched"}