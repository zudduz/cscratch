import uuid
import logging
import datetime

# Relative Imports
from . import persistence
from .ai_engine import AITool
from .models import GameState, Player, GameInterface

ai_tool = AITool()

class Toolbox:
    def __init__(self):
        self.ai = ai_tool

async def load_cartridge(cartridge_id: str):
    try:
        if cartridge_id == "hms-bucket":
            from cartridges.hms_bucket.logic import HMSBucket
            return HMSBucket()
        elif cartridge_id == "foster-protocol":
            from cartridges.foster_protocol.logic import FosterProtocol
            return FosterProtocol()
        else:
            from cartridges.hms_bucket.logic import HMSBucket
            return HMSBucket()
    except Exception as e:
        logging.error(f"Failed to load cartridge {cartridge_id}: {e}")
        raise e

async def start_new_game(story_id: str = "hms-bucket") -> str:
    game_id = str(uuid.uuid4())[:8]
    cartridge = await load_cartridge(story_id)
    logging.info(f"Game Engine: Creating Lobby for {game_id}")
    
    new_game = GameState(
        id=game_id,
        story_id=story_id,
        status="setup",
        created_at=datetime.datetime.now(datetime.timezone.utc),
        metadata=cartridge.meta
    )
    
    await persistence.db.create_game_record(new_game)
    return game_id

async def register_interface(game_id: str, interface_data: dict):
    interface = GameInterface(**interface_data)
    await persistence.db.update_game_interface(game_id, interface)

async def join_game(game_id: str, user_id: str, user_name: str):
    player = Player(
        id=user_id,
        name=user_name,
        joined_at=str(uuid.uuid1())
    )
    await persistence.db.add_player_to_game(game_id, player)
    logging.info(f"Player {user_name} joined game {game_id}")

async def launch_match(game_id: str):
    await persistence.db.set_game_active(game_id)
    logging.info(f"Game {game_id} is now ACTIVE")

async def find_game_by_channel(channel_id: str) -> GameState | None:
    return await persistence.db.get_game_by_channel_id(channel_id)

async def end_game(game_id: str):
    await persistence.db.mark_game_ended(game_id)

async def process_player_input(channel_id: str, channel_name: str, user_id: str, user_name: str, user_input: str) -> str:
    # 1. Look up Game
    game: GameState = await persistence.db.get_game_by_channel_id(channel_id)
    if not game: return "Error: Game not found."
    
    if game.status == 'setup': return None 
    if game.status != 'active': return "Error: Game is not active."

    # 2. Build Context
    # This dictionary carries all the metadata the cartridge needs
    context = {
        "channel_id": str(channel_id),
        "channel_name": str(channel_name),
        "user_id": str(user_id),
        "user_name": str(user_name),
        "interface": game.interface.model_dump()
    }

    # 3. Load Cartridge
    story_id = game.story_id
    cartridge = await load_cartridge(story_id)
    tools = Toolbox()
    
    # 4. Handover to Cartridge
    result = await cartridge.handle_input(game.model_dump(), user_input, context, tools)
    
    # 5. Persist Changes (Naive update for now)
    # In a real impl, we should check if result['state_update'] actually changed
    # For now, we rely on the cartridge to modify the state dictionary
    
    return result['response']
