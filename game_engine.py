import datetime
import uuid
import logging
from google.cloud.firestore import AsyncClient

# Initialize DB for Game State
firestore_client = AsyncClient(database="sandbox")

async def start_new_game(story_id: str = "sleeping-agent") -> str:
    """
    Domain Logic: Starts a new game session.
    1. Generates a unique Game ID.
    2. Creates the initial game record in persistence.
    Returns: The new Game ID.
    """
    game_id = str(uuid.uuid4())[:8]
    
    try:
        # Create the logical game record
        # Note: We don't store channel IDs here yet, because the UI hasn't built them.
        await firestore_client.collection("games").document(game_id).set({
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "status": "initializing",
            "story_id": story_id,
            "metadata": {} 
        })
        logging.info(f"Game Engine: Initialized new game {game_id}")
        return game_id
    except Exception as e:
        logging.error(f"Game Engine Error: {e}")
        raise e

async def register_interface(game_id: str, interface_data: dict):
    """
    Domain Logic: Binds a UI interface (Discord Channel, Web Socket, etc) to a Game.
    """
    try:
        await firestore_client.collection("games").document(game_id).update({
            "status": "active",
            "interface": interface_data
        })
        logging.info(f"Game Engine: Bound interface to game {game_id}")
    except Exception as e:
        logging.error(f"Game Engine Error binding interface: {e}")
        raise e
