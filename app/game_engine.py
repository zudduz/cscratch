import uuid
import logging

# Import the Data Layer (Relative Import Fixed)
from . import persistence

async def start_new_game(story_id: str = "sleeping-agent") -> str:
    game_id = str(uuid.uuid4())[:8]
    logging.info(f"Game Engine: Initializing game {game_id}")
    await persistence.create_game_record(game_id, story_id)
    return game_id

async def register_interface(game_id: str, interface_data: dict):
    logging.info(f"Game Engine: Binding interface to {game_id}")
    await persistence.update_game_interface(game_id, interface_data)

async def find_game_by_channel(channel_id: str) -> dict | None:
    return await persistence.get_game_by_channel_id(channel_id)

async def end_game(game_id: str):
    logging.info(f"Game Engine: Ending game {game_id}")
    await persistence.mark_game_ended(game_id)
