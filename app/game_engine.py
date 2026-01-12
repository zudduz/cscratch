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

async def process_player_input(channel_id: str, user_input: str) -> str:
    game: GameState = await persistence.db.get_game_by_channel_id(channel_id)
    if not game: return "Error: Game not found."
    
    if game.status == 'setup':
        return None 

    if game.status != 'active': return "Error: Game is not active."

    story_id = game.story_id
    cartridge = await load_cartridge(story_id)
    tools = Toolbox()
    
    # NEW: Context Object
    # We pass the channel_id so the cartridge knows WHERE this was said
    context = {
        "channel_id": str(channel_id),
        "interface": game.interface.model_dump()
    }
    
    # CHANGED: play_turn -> handle_input
    # We pass the generic dict to the cartridge, it handles the Typed Model inflation internally
    result = await cartridge.handle_input(game.model_dump(), user_input, context, tools)
    
    # Save any state changes returned by the cartridge
    if result.get("state_update"):
        # This is a bit of a hack: we need a proper update method in persistence
        # For now, we rely on the fact that persistence doesn't have a generic update_state yet.
        # We will assume the cartridge modifies the object in place or returns a dict to merge.
        # TODO: Implement persistence.db.update_game_state(game_id, result['state_update'])
        pass

    return result['response']
