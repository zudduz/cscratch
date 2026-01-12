import datetime
import logging
from google.cloud.firestore import AsyncClient
from google.api_core.exceptions import AlreadyExists

db = AsyncClient(database="sandbox")
CURRENT_SCHEMA_VERSION = 2 # Bumped for 'players' field

async def lock_event(event_id: str) -> bool:
    try:
        await db.collection("processed_messages").document(str(event_id)).create({
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "status": "processing"
        })
        return True
    except AlreadyExists:
        return False
    except Exception as e:
        logging.error(f"Persistence Error locking event: {e}")
        return False

async def create_game_record(game_id: str, story_id: str, metadata: dict = None):
    try:
        # STATUS starts as 'setup', not 'active'
        await db.collection("games").document(game_id).set({
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "status": "setup", 
            "story_id": story_id,
            "metadata": metadata or {},
            "players": [], # New Field
            "schema_version": CURRENT_SCHEMA_VERSION,
            "interface": {} 
        })
    except Exception as e:
        logging.error(f"Persistence Error creating game: {e}")
        raise e

async def add_player_to_game(game_id: str, player_data: dict):
    try:
        # Atomic array union
        await db.collection("games").document(game_id).update({
            "players": db.field_path("players", "array_union", [player_data])
        })
    except Exception as e:
        logging.error(f"Persistence Error adding player: {e}")
        raise e

async def set_game_active(game_id: str):
    try:
        await db.collection("games").document(game_id).update({
            "status": "active",
            "started_at": datetime.datetime.now(datetime.timezone.utc)
        })
    except Exception as e:
        logging.error(f"Persistence Error starting game: {e}")
        raise e

async def update_game_interface(game_id: str, interface_data: dict):
    try:
        await db.collection("games").document(game_id).update({
            "interface": interface_data
        })
    except Exception as e:
        logging.error(f"Persistence Error updating interface: {e}")
        raise e

async def get_game_by_channel_id(channel_id: str) -> dict | None:
    try:
        games_ref = db.collection("games")
        # Allow finding games in 'setup' OR 'active' state
        query = games_ref.where("interface.channel_id", "==", str(channel_id)).limit(1)
        async for doc in query.stream():
            data = doc.to_dict()
            data['id'] = doc.id
            return data
        return None
    except Exception as e:
        logging.error(f"Persistence Error finding game: {e}")
        return None

async def mark_game_ended(game_id: str):
    try:
        await db.collection("games").document(game_id).update({
            "status": "ended",
            "ended_at": datetime.datetime.now(datetime.timezone.utc)
        })
    except Exception as e:
        logging.error(f"Persistence Error ending game: {e}")
        raise e

async def get_active_game_channels() -> set:
    active_ids = set()
    try:
        # Get both Setup and Active games so buttons/chat work
        query = db.collection("games").where("status", "in", ["active", "setup"])
        async for doc in query.stream():
            data = doc.to_dict()
            interface = data.get('interface', {})
            c_id = interface.get('channel_id')
            if c_id:
                active_ids.add(str(c_id))
        logging.info(f"Persistence: Hydrated cache with {len(active_ids)} channels.")
        return active_ids
    except Exception as e:
        logging.error(f"Persistence Error hydrating cache: {e}")
        return set()
