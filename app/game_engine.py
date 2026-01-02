import uuid
import logging

# Import the Data Layer
import persistence

async def start_new_game(story_id: str = "sleeping-agent") -> str:
    """
    Domain Logic: Starts a new game session.
    """
    # Logic: Generate the ID
    game_id = str(uuid.uuid4())[:8]
    logging.info(f"Game Engine: Initializing game {game_id}")
    
    # Persistence: Save the record
    await persistence.create_game_record(game_id, story_id)
    
    return game_id

async def register_interface(game_id: str, interface_data: dict):
    """
    Domain Logic: Binds a UI interface to a Game.
    """
    logging.info(f"Game Engine: Binding interface to {game_id}")
    await persistence.update_game_interface(game_id, interface_data)

async def find_game_by_channel(channel_id: str) -> dict | None:
    """
    Domain Logic: specific lookup for Discord channel IDs.
    """
    return await persistence.get_game_by_channel_id(channel_id)

async def end_game(game_id: str):
    """
    Domain Logic: Termination sequence.
    """
    logging.info(f"Game Engine: Ending game {game_id}")
    await persistence.mark_game_ended(game_id)
