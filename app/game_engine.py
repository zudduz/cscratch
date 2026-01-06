import uuid
import logging
import importlib

# Relative Imports
from . import persistence
from .ai_engine import AITool

# Initialize Tools (The "Console Hardware")
ai_tool = AITool()

class Toolbox:
    def __init__(self):
        self.ai = ai_tool

async def load_cartridge(cartridge_id: str):
    """
    Dynamically imports the cartridge module.
    """
    try:
        # For now, we map 'hms-bucket' to the python class
        if cartridge_id == "hms-bucket":
            from cartridges.hms_bucket.logic import HMSBucket
            return HMSBucket()
        else:
            # Fallback for legacy tests
            from cartridges.hms_bucket.logic import HMSBucket
            return HMSBucket()
    except Exception as e:
        logging.error(f"Failed to load cartridge {cartridge_id}: {e}")
        raise e

async def start_new_game(story_id: str = "hms-bucket") -> str:
    game_id = str(uuid.uuid4())[:8]
    logging.info(f"Game Engine: Initializing game {game_id} with cartridge {story_id}")
    
    # 1. Load Cartridge to get metadata/defaults
    cartridge = await load_cartridge(story_id)
    
    # 2. Save Initial Record
    await persistence.create_game_record(game_id, story_id, metadata=cartridge.meta)
    
    return game_id

async def register_interface(game_id: str, interface_data: dict):
    await persistence.update_game_interface(game_id, interface_data)

async def find_game_by_channel(channel_id: str) -> dict | None:
    return await persistence.get_game_by_channel_id(channel_id)

async def kill_game(game_id: str):
    await persistence.mark_game_ended(game_id)

# TODO Add user_id/handle
async def process_player_input(channel_id: str, user_input: str) -> str:
    """
    Main Entry Point for gameplay.
    1. Find Game
    2. Load Cartridge
    3. Run Turn
    4. Save State
    """
    # 1. Lookup Game
    game_data = await persistence.get_game_by_channel_id(channel_id)
    if not game_data:
        return "Error: Game not found."
    
    if game_data.get('status') != 'active':
        return "Error: Game is not active."

    game_id = game_data['id']
    story_id = game_data.get('story_id', 'hms-bucket')
    current_state = game_data # In the future, this might be a sub-field 'game_state'

    # 2. Load Cartridge
    cartridge = await load_cartridge(story_id)
    
    # 3. Play Turn (The Cartridge decides what happens)
    # We pass the Toolbox so the cartridge can use the AI
    tools = Toolbox()
    result = await cartridge.play_turn(current_state, user_input, tools)
    
    # 4. Save State (Optional - if cartridge modified it)
    # await persistence.update_game_state(game_id, result['state_update'])
    
    return result['response']
