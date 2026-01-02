import datetime
import uuid
import logging
from google.cloud.firestore import AsyncClient

# Initialize DB for Game State
firestore_client = AsyncClient(database="sandbox")

async def start_new_game(story_id: str = "sleeping-agent") -> str:
    """
    Domain Logic: Starts a new game session.
    """
    game_id = str(uuid.uuid4())[:8]
    
    try:
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
    Domain Logic: Binds a UI interface (Discord Channel) to a Game.
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

async def find_game_by_channel(channel_id: str) -> dict | None:
    """
    Domain Logic: Looks up the game associated with a specific channel ID.
    Returns the game data dict (including ID) or None if not found.
    """
    try:
        # Query for the game where interface.channel_id matches
        games_ref = firestore_client.collection("games")
        query = games_ref.where("interface.channel_id", "==", str(channel_id)).limit(1)
        
        async for doc in query.stream():
            data = doc.to_dict()
            data['id'] = doc.id  # Attach the ID for convenience
            return data
            
        return None
    except Exception as e:
        logging.error(f"Game Engine Lookup Error: {e}")
        return None