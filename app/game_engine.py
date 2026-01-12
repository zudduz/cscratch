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
        logging.info(f"Engine: Loading cartridge '{cartridge_id}'...")
        
        if cartridge_id == "hms-bucket":
            from cartridges.hms_bucket.logic import HMSBucket
            return HMSBucket()
            
        elif cartridge_id == "foster-protocol":
            # NEW: Wiring up the Foster Protocol
            from cartridges.foster_protocol.logic import FosterProtocol
            return FosterProtocol()
            
        else:
            # Fallback
            logging.warning(f"Cartridge '{cartridge_id}' not found. Loading Default.")
            from cartridges.hms_bucket.logic import HMSBucket
            return HMSBucket()
            
    except Exception as e:
        logging.error(f"Failed to load cartridge {cartridge_id}: {e}")
        raise e

async def start_new_game(story_id: str = "hms-bucket") -> str:
    game_id = str(uuid.uuid4())[:8]
    
    # 1. Load Cartridge to get metadata
    cartridge = await load_cartridge(story_id)
    
    # 2. Save Initial Record
    logging.info(f"Game Engine: Initializing game {game_id} ({cartridge.meta['name']})")
    await persistence.create_game_record(game_id, story_id, metadata=cartridge.meta)
    
    return game_id

async def register_interface(game_id: str, interface_data: dict):
    await persistence.update_game_interface(game_id, interface_data)

async def find_game_by_channel(channel_id: str) -> dict | None:
    return await persistence.get_game_by_channel_id(channel_id)

async def end_game(game_id: str):
    await persistence.mark_game_ended(game_id)

async def process_player_input(channel_id: str, user_input: str) -> str:
    # 1. Lookup Game
    game_data = await persistence.get_game_by_channel_id(channel_id)
    if not game_data: return "Error: Game not found."
    if game_data.get('status') != 'active': return "Error: Game is not active."

    # 2. Load Cartridge
    story_id = game_data.get('story_id', 'hms-bucket')
    cartridge = await load_cartridge(story_id)
    
    # 3. Play Turn
    tools = Toolbox()
    result = await cartridge.play_turn(game_data, user_input, tools)
    
    return result['response']
