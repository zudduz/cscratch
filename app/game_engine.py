import uuid
import logging
import datetime
from . import persistence
from .ai_engine import AITool
from .models import GameState, Player, GameInterface

ai_tool = AITool()

class Toolbox:
    def __init__(self):
        self.ai = ai_tool

async def load_cartridge(cartridge_id: str):
    if cartridge_id == "hms-bucket":
        from cartridges.hms_bucket.logic import HMSBucket
        return HMSBucket()
    elif cartridge_id == "foster-protocol":
        from cartridges.foster_protocol.logic import FosterProtocol
        return FosterProtocol()
    return HMSBucket()

async def start_new_game(story_id: str, host_id: str, host_name: str) -> str:
    game_id = str(uuid.uuid4())[:8]
    cartridge = await load_cartridge(story_id)
    
    logging.info(f"Game Engine: Creating Lobby for {game_id} (Host: {host_name})")
    
    new_game = GameState(
        id=game_id,
        story_id=story_id,
        host_id=host_id,  # Record Host
        status="setup",
        created_at=datetime.datetime.now(datetime.timezone.utc),
        metadata=cartridge.meta
    )
    
    # 1. Create Record
    await persistence.db.create_game_record(new_game)
    
    # 2. Auto-join Host
    await join_game(game_id, host_id, host_name)
    
    return game_id

async def register_interface(game_id: str, interface_data: dict):
    interface = GameInterface(**interface_data)
    await persistence.db.update_game_interface(game_id, interface)

async def join_game(game_id: str, user_id: str, user_name: str):
    # Check if already joined to avoid duplicates
    game = await persistence.db.get_game_by_id(game_id)
    if game:
        for p in game.players:
            if p.id == user_id:
                logging.info(f"Player {user_name} already in game {game_id}")
                return

    player = Player(id=user_id, name=user_name, joined_at=str(uuid.uuid1()))
    await persistence.db.add_player_to_game(game_id, player)
    logging.info(f"Player {user_name} joined game {game_id}")

async def launch_match(game_id: str) -> dict:
    game = await persistence.db.get_game_by_id(game_id)
    if not game: return None

    cartridge = await load_cartridge(game.story_id)
    result = {}
    
    if hasattr(cartridge, 'on_game_start'):
        result = await cartridge.on_game_start(game.model_dump())
        if 'metadata' in result:
             await persistence.db.update_game_metadata(game_id, result['metadata'])

    await persistence.db.set_game_active(game_id)
    logging.info(f"Game {game_id} initialized and ACTIVE")
    return result

async def find_game_by_channel(channel_id: str) -> GameState | None:
    return await persistence.db.get_game_by_channel_id(channel_id)

async def end_game(game_id: str):
    await persistence.db.mark_game_ended(game_id)

async def process_player_input(channel_id: str, channel_name: str, user_id: str, user_name: str, user_input: str) -> str:
    res = await process_player_input_full(channel_id, channel_name, user_id, user_name, user_input)
    if res: return res.get('response')
    return None

async def process_player_input_full(channel_id: str, channel_name: str, user_id: str, user_name: str, user_input: str) -> dict:
    game = await persistence.db.get_game_by_channel_id(channel_id)
    if not game or game.status != 'active': return None
    
    context = {
        "channel_id": str(channel_id),
        "channel_name": str(channel_name),
        "user_id": str(user_id),
        "user_name": str(user_name),
        "interface": game.interface.model_dump()
    }
    
    cartridge = await load_cartridge(game.story_id)
    result = await cartridge.handle_input(game.model_dump(), user_input, context, Toolbox())
    result['game_id'] = game.id
    
    if result.get("state_update"):
         await persistence.db.update_game_metadata(game.id, result['state_update']['metadata'])

    return result
