import datetime
import logging
from google.cloud.firestore import AsyncClient
from google.api_core.exceptions import AlreadyExists

# Initialize shared DB Client
# We use a single client for the app to reuse connection pools
db = AsyncClient(database="sandbox")

# DATA MODEL VERSION
CURRENT_SCHEMA_VERSION = 1

# --- IDEMPOTENCY (Locking) ---
async def lock_event(event_id: str) -> bool:
    """
    Attempts to create a lock document for a specific event ID.
    Returns True if lock acquired (first time), False if already exists.
    """
    try:
        await db.collection("processed_messages").document(str(event_id)).create({
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "status": "processing"
        })
        return True
    except AlreadyExists:
        logging.warning(f"Persistence: Event {event_id} already processed.")
        return False
    except Exception as e:
        logging.error(f"Persistence Error locking event: {e}")
        return False

# --- GAME CRUD OPERATIONS ---
async def create_game_record(game_id: str, story_id: str, metadata: dict = None):
    try:
        await db.collection("games").document(game_id).set({
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "status": "initializing",
            "story_id": story_id,
            "metadata": metadata or {},
            "schema_version": CURRENT_SCHEMA_VERSION
        })
    except Exception as e:
        logging.error(f"Persistence Error creating game: {e}")
        raise e

async def update_game_interface(game_id: str, interface_data: dict):
    try:
        await db.collection("games").document(game_id).update({
            "status": "active",
            "interface": interface_data
        })
    except Exception as e:
        logging.error(f"Persistence Error updating interface: {e}")
        raise e

async def get_game_by_channel_id(channel_id: str) -> dict | None:
    try:
        games_ref = db.collection("games")
        # Query: Find game where interface.channel_id == X
        query = games_ref.where("interface.channel_id", "==", str(channel_id)).limit(1)
        
        async for doc in query.stream():
            data = doc.to_dict()
            data['id'] = doc.id
            # Hook for future schema migrations would go here
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