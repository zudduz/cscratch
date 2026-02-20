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
# Maps command keys (e.g. "start", "admin.gift") to handler functions
REGISTRY: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Awaitable[None]]] = {}

UI_MAP = {
    "foster-protocol": ("cartridges.foster_protocol.ui_templates", "FosterPresenter")
}

async def _get_ui_presenter(ctx: Dict[str, Any], params: Dict[str, Any]):
    """Dynamically loads the UI Presenter for the current game context."""
    cartridge_id = params.get("cartridge")
    
    # If not explicitly provided, try to infer from the channel's active game
    if not cartridge_id:
        channel_id = ctx.get("channel_id")
        if channel_id:
            game_id = await persistence.db.get_game_id_by_channel_index(channel_id)
            if game_id:
                game = await persistence.db.get_game_by_id(game_id)
                if game:
                    cartridge_id = game.story_id
                    
    # Fallback to default
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

@slash_command("start")
async def handle_start(ctx: Dict[str, Any], params: Dict[str, Any]):
    cartridge = params.get("cartridge", "foster-protocol")
    user_id = ctx["user_id"]
    guild_id = ctx["guild_id"]
    channel_id = ctx["channel_id"]
    
    try:
        # 1. Create Game Record
        game_id = await game_engine.engine.start_new_game(cartridge, user_id, ctx["user_name"])
        
        # 2. Create Channels
        # Note: discord_client is "stateless" but holds a client reference we can use for API calls
        guild = await discord_client.client.client.fetch_guild(int(guild_id))
        
        cat = await guild.create_category(f"Lobby {game_id}")
        chan = await guild.create_text_channel("cscratch-lobby", category=cat)
        
        # 3. Register Interface
        await game_engine.engine.register_interface_data(game_id, {
            "type": "discord",
            "guild_id": guild_id,
            "category_id": str(cat.id),
            "main_channel_id": str(chan.id),
            "listener_ids": [str(chan.id)]
        })
        
        # 4. Update Index
        await persistence.db.register_channel_association(str(chan.id), game_id)
        
        # 5. Send Lobby UI
        embed = discord.Embed(
            title=presentation.format_lobby_title(cartridge),
            description=presentation.LOBBY_DESC,
            color=0x00ff00
        )
        
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label=presentation.BTN_JOIN, style=discord.ButtonStyle.green, custom_id="join_btn"))
        view.add_item(discord.ui.Button(label=presentation.BTN_START, style=discord.ButtonStyle.danger, custom_id="start_btn"))
        
        await chan.send(embed=embed, view=view)

        # 6. Host Fair Play Check
        await discord_client.client.check_and_warn_admin(guild_id, user_id, str(chan.id))
        
        # Notify origin channel
        await discord_client.client.send_message(channel_id, presentation.format_lobby_created_msg(chan.mention))
        
    except Exception as e:
        logging.error(f"Start CMD Failed: {e}")
        await discord_client.client.send_message(channel_id, presentation.CMD_FAILED.format(error=str(e)))

@slash_command("end")
async def handle_end(ctx: Dict[str, Any], params: Dict[str, Any]):
    channel_id = ctx["channel_id"]
    game_id = await persistence.db.get_game_id_by_channel_index(channel_id)
    
    if not game_id:
        await discord_client.client.send_message(channel_id, presentation.ERR_NO_GAME)
        return

    game = await persistence.db.get_game_by_id(game_id)
    
    if not game:
        await discord_client.client.send_message(channel_id, presentation.ERR_NO_GAME)
        return
        
    if ctx["user_id"] != game.host_id:
        await discord_client.client.send_message(channel_id, presentation.ERR_NOT_HOST)
        return
        
    await discord_client.client.send_message(channel_id, presentation.MSG_TEARDOWN)
    
    await discord_client.client.cleanup_game_channels(ctx["guild_id"], game.interface.model_dump())
    await game_engine.engine.end_game(game.id)

@slash_command("cscratch.balance") # Handling namespaced
@slash_command("balance")          # Handling root (just in case)
async def handle_balance(ctx: Dict[str, Any], params: Dict[str, Any]):
    user_id = ctx["user_id"]
    balance = await persistence.db.get_user_balance(user_id)
    report = presentation.format_balance_report(user_id, balance)
    
    if ctx.get("interaction_token"):
        await discord_client.client.edit_response(
            ctx["interaction_token"], 
            ctx["application_id"], 
            report
        )
    else:
        await discord_client.client.send_message(ctx["channel_id"], report)

@slash_command("cscratch.guide")
@slash_command("guide")
async def handle_guide(ctx: Dict[str, Any], params: Dict[str, Any]):
    try:
        presenter = await _get_ui_presenter(ctx, params)
        text = getattr(presenter, "GUIDE_TEXT", "Guide not found for this cartridge.")
    except Exception as e:
        text = f"Failed to load guide: {e}"

    if ctx.get("interaction_token"):
        await discord_client.client.edit_response(
            ctx["interaction_token"], 
            ctx["application_id"], 
            text
        )
    else:
        await discord_client.client.send_message(ctx["channel_id"], text)

@slash_command("cscratch.manual")
@slash_command("manual")
async def handle_manual(ctx: Dict[str, Any], params: Dict[str, Any]):
    try:
        presenter = await _get_ui_presenter(ctx, params)
        text = getattr(presenter, "MANUAL_TEXT", "Manual not found for this cartridge.")
    except Exception as e:
        text = f"Failed to load manual: {e}"

    if ctx.get("interaction_token"):
        await discord_client.client.edit_response(
            ctx["interaction_token"], 
            ctx["application_id"], 
            text
        )
    else:
        await discord_client.client.send_message(ctx["channel_id"], text)

# @slash_command("admin.gift")
# async def handle_gift(ctx: Dict[str, Any], params: Dict[str, Any]):
#     sender_id = ctx["user_id"]
    
#     # 1. Admin Check
#     if sender_id not in config.ADMIN_USER_IDS:
#         await discord_client.client.send_message(ctx["channel_id"], presentation.ERR_DENIED_ADMIN)
#         return

#     target_id = params.get("recipient")
#     amount = params.get("amount")
    
#     if not target_id or amount is None:
#         return 

#     # 2. Execute Transfer (Minting)
#     new_bal = await persistence.db.adjust_user_balance(target_id, int(amount))
    
#     await discord_client.client.send_message(
#         ctx["channel_id"], 
#         presentation.format_gift_report(amount, target_id, new_bal)
#     )

# @slash_command("admin.balance")
# async def handle_admin_balance(ctx: Dict[str, Any], params: Dict[str, Any]):
#     sender_id = ctx["user_id"]
    
#     # 1. Admin Check
#     if sender_id not in config.ADMIN_USER_IDS:
#         await discord_client.client.send_message(ctx["channel_id"], presentation.ERR_DENIED_ADMIN)
#         return

#     target_id = params.get("user")
#     if not target_id:
#         return

#     balance = await persistence.db.get_user_balance(target_id)
#     await discord_client.client.send_message(
#         ctx["channel_id"], 
#         presentation.format_admin_balance_report(target_id, balance)
#     )