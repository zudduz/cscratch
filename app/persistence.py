import datetime
import logging
from google.cloud.firestore import AsyncClient
from google.api_core.exceptions import AlreadyExists

# Initialize shared DB Client
db = AsyncClient(database="sandbox")
CURRENT_SCHEMA_VERSION = 1

# --- IDEMPOTENCY ---
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

# --- GAME CRUD ---
async def create_game_record(game_id: str, story_id: str, metadata: dict = None):
    try:
        await db.collection("games").document(game_id).set({
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "status": "active", # Active immediately for now
            "story_id": story_id,
            "metadata": metadata or {},
            "schema_version": CURRENT_SCHEMA_VERSION,
            "interface": {} # Will be populated shortly
        })
    except Exception as e:
        logging.error(f"Persistence Error creating game: {e}")
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
        # Firestore auto-indexes nested fields (interface.channel_id)
        games_ref = db.collection("games")
        query = games_ref.where("interface.channel_id", "==", str(channel_id)).where("status", "==", "active").limit(1)
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

# --- NEW: CACHE HYDRATION ---
async def get_active_game_channels() -> set:
    """
    Returns a set of all Channel IDs (strings) that belong to active games.
    Used to hydrate the in-memory cache on bot startup.
    """
    active_ids = set()
    try:
        # Query all active games
        # Projection: We only need the interface field to save bandwidth
        query = db.collection("games").where("status", "==", "active")
        
        async for doc in query.stream():
            data = doc.to_dict()
            interface = data.get('interface', {})
            c_id = interface.get('channel_id')
            if c_id:
                active_ids.add(str(c_id))
                
        logging.info(f"Persistence: Hydrated cache with {len(active_ids)} active channels.")
        return active_ids
    except Exception as e:
        logging.error(f"Persistence Error hydrating cache: {e}")
        return set()
