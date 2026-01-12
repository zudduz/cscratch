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

async def start_new_game(story_id: str = "hms-bucket") -> str:
    game_id = str(uuid.uuid4())[:8]
    cartridge = await load_cartridge(story_id)
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
    player = Player(id=user_id, name=user_name, joined_at=str(uuid.uuid1()))
    await persistence.db.add_player_to_game(game_id, player)

async def launch_match(game_id: str):
    # 1. Fetch Game State
    # Note: We are adding get_game_by_id to persistence in the next file block
    game = await persistence.db.get_game_by_id(game_id)
    if not game:
        logging.error(f"Cannot launch match {game_id}: Not found")
        return

    # 2. Run Start Hook
    cartridge = await load_cartridge(game.story_id)
    
    # Check if cartridge has on_game_start
    if hasattr(cartridge, 'on_game_start'):
        updated_state_dict = await cartridge.on_game_start(game.model_dump())
        
        # 3. Update DB with new Metadata (Bots/Roles)
        # We need to save the metadata back
        # Ideally persistence should have a full update, but for now:
        await persistence.db.update_game_metadata(game_id, updated_state_dict['metadata'])

    # 4. Set Active
    await persistence.db.set_game_active(game_id)
    logging.info(f"Game {game_id} initialized and ACTIVE")

async def find_game_by_channel(channel_id: str) -> GameState | None:
    return await persistence.db.get_game_by_channel_id(channel_id)

async def end_game(game_id: str):
    await persistence.db.mark_game_ended(game_id)

async def process_player_input(channel_id: str, channel_name: str, user_id: str, user_name: str, user_input: str) -> str:
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
    
    # Save changes (Quick hack: we trust the cartridge returns the full state)
    if result.get("state_update"):
         await persistence.db.update_game_metadata(game.id, result['state_update']['metadata'])

    return result['response']
