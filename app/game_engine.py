import uuid
import logging
import importlib

# Relative Imports
from . import persistence
from .ai_engine import AITool

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
    # Status is 'setup' by default in persistence
    await persistence.create_game_record(game_id, story_id, metadata=cartridge.meta)
    return game_id

async def register_interface(game_id: str, interface_data: dict):
    await persistence.update_game_interface(game_id, interface_data)

async def join_game(game_id: str, user_id: str, user_name: str):
    # Business Logic: Can add max player check here
    await persistence.add_player_to_game(game_id, {
        "id": user_id,
        "name": user_name,
        "joined_at": str(uuid.uuid1())
    })
    logging.info(f"Player {user_name} joined game {game_id}")

async def launch_match(game_id: str):
    # Transition from Lobby -> Active
    await persistence.set_game_active(game_id)
    logging.info(f"Game {game_id} is now ACTIVE")

async def find_game_by_channel(channel_id: str) -> dict | None:
    return await persistence.get_game_by_channel_id(channel_id)

async def end_game(game_id: str):
    await persistence.mark_game_ended(game_id)

async def process_player_input(channel_id: str, user_input: str) -> str:
    game_data = await persistence.get_game_by_channel_id(channel_id)
    if not game_data: return "Error: Game not found."
    
    # If in Setup mode, ignore chat (or maybe handle chat as lobby chat?)
    if game_data.get('status') == 'setup':
        return None # Silent in lobby

    if game_data.get('status') != 'active': return "Error: Game is not active."

    story_id = game_data.get('story_id', 'hms-bucket')
    cartridge = await load_cartridge(story_id)
    tools = Toolbox()
    result = await cartridge.play_turn(game_data, user_input, tools)
    return result['response']
