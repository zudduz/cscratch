import logging
import discord
from typing import Dict, Any, Callable, Awaitable

from . import persistence
from . import game_engine
from . import discord_client
from . import presentation
from . import config
import importlib

# --- REGISTRY ---
REGISTRY: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Awaitable[None]]] = {}

UI_MAP = {
    "foster-protocol": ("cartridges.foster_protocol.ui_templates", "FosterPresenter")
}

async def _get_ui_presenter(ctx: Dict[str, Any], params: Dict[str, Any]):
    cartridge_id = params.get("cartridge")
    if not cartridge_id:
        channel_id = ctx.get("channel_id")
        if channel_id:
            game_id = await persistence.db.get_game_id_by_channel_index(channel_id)
            if game_id:
                game = await persistence.db.get_game_by_id(game_id)
                if game:
                    cartridge_id = game.story_id
    cartridge_id = cartridge_id or "foster-protocol"
    module_path, class_name = UI_MAP.get(cartridge_id, UI_MAP["foster-protocol"])
    module = importlib.import_module(module_path)
    return getattr(module, class_name)

def slash_command(name: str):
    def decorator(func):
        REGISTRY[name] = func
        return func
    return decorator

# --- HANDLERS ---

@slash_command("cscratch.lobby")
@slash_command("lobby")
async def handle_lobby(ctx: Dict[str, Any], params: Dict[str, Any]):
    cartridge = params.get("cartridge", "foster-protocol")
    
    try:
        await game_engine.engine.setup_game(
            story_id=cartridge, 
            host_id=ctx["user_id"], 
            host_name=ctx["user_name"],
            guild_id=ctx["guild_id"],
            origin_channel_id=ctx["channel_id"]
        )
        await discord_client.client.delete_response(
            ctx["interaction_token"], 
            ctx["application_id"]
        )
    except ValueError as ve:
        err_str = str(ve)
        if err_str == "NO_CATEGORY":
            await discord_client.client.edit_response(
                ctx["interaction_token"], 
                ctx["application_id"], 
                presentation.ERR_NO_CATEGORY
            )
        elif err_str.startswith("MISSING_BOT_PERMS"):
            missing = err_str.split(":", 1)[1] if ":" in err_str else "Unknown"
            await discord_client.client.edit_response(
                ctx["interaction_token"], 
                ctx["application_id"], 
                presentation.ERR_MISSING_BOT_PERMS.format(missing=missing)
            )
        else:
            await discord_client.client.edit_response(
                ctx["interaction_token"], ctx["application_id"], presentation.CMD_FAILED.format(error=err_str)
            )
    except Exception as e:
        logging.error(f"Lobby CMD Failed: {e}")
        await discord_client.client.edit_response(
            ctx["interaction_token"], 
            ctx["application_id"], 
            presentation.CMD_FAILED.format(error=str(e))
        )

@slash_command("cscratch.kill")
@slash_command("kill")
async def handle_kill(ctx: Dict[str, Any], params: Dict[str, Any]):
    channel_id = ctx["channel_id"]
    token = ctx["interaction_token"]
    app_id = ctx["application_id"]

    game_id = await persistence.db.get_game_id_by_channel_index(channel_id)
    if not game_id:
        await discord_client.client.edit_response(token, app_id, presentation.ERR_NO_GAME)
        return

    game = await persistence.db.get_game_by_id(game_id)
    if not game:
        await discord_client.client.edit_response(token, app_id, presentation.ERR_NO_GAME)
        return
        
    if ctx["user_id"] != game.host_id:
        await discord_client.client.edit_response(token, app_id, presentation.ERR_NOT_HOST)
        return
        
    lobby_name = presentation.format_lobby_title(game.story_id, game.interface.callsign or "UNK")
    await discord_client.client.edit_response(token, app_id, presentation.format_teardown(lobby_name))
    
    await discord_client.client.cleanup_game_channels(ctx["guild_id"], game.interface.model_dump())
    await game_engine.engine.end_game(game.id)

@slash_command("cscratch.balance")
@slash_command("balance")
async def handle_balance(ctx: Dict[str, Any], params: Dict[str, Any]):
    user_id = ctx["user_id"]
    balance = await persistence.db.get_user_balance(user_id)
    report = presentation.format_balance_report(user_id, balance)
    
    if ctx.get("interaction_token"):
        await discord_client.client.edit_response(
            ctx["interaction_token"], ctx["application_id"], report
        )
    else:
        await discord_client.client.send_message(ctx["channel_id"], report)

async def _handle_info_command(ctx: Dict[str, Any], params: Dict[str, Any], attr_name: str, doc_name: str):
    channel_id = ctx["channel_id"]
    game_id = await persistence.db.get_game_id_by_channel_index(channel_id)
    
    if not game_id:
        text = presentation.ERR_NO_ACTIVE_GAME
    else:
        try:
            presenter = await _get_ui_presenter(ctx, params)
            text = getattr(presenter, attr_name, presentation.ERR_DOC_NOT_FOUND.format(doc_name=doc_name))
        except Exception as e:
            text = presentation.ERR_DOC_LOAD_FAILED.format(doc_name=doc_name, error=str(e))

    if ctx.get("interaction_token"):
        await discord_client.client.edit_response(ctx["interaction_token"], ctx["application_id"], text)
    else:
        await discord_client.client.send_message(channel_id, text)

@slash_command("cscratch.guide")
@slash_command("guide")
async def handle_guide(ctx: Dict[str, Any], params: Dict[str, Any]):
    await _handle_info_command(ctx, params, "GUIDE_TEXT", "Guide")

@slash_command("cscratch.manual")
@slash_command("manual")
async def handle_manual(ctx: Dict[str, Any], params: Dict[str, Any]):
    await _handle_info_command(ctx, params, "MANUAL_TEXT", "Manual")