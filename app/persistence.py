import datetime
import logging
from google.cloud.firestore import AsyncClient, ArrayUnion
from google.api_core.exceptions import AlreadyExists
from .models import GameState, Player, GameInterface

class GameDatabase:
    def __init__(self):
        self.client = AsyncClient(database="sandbox")

    # ... [Existing Methods kept same] ...
    async def lock_event(self, event_id: str) -> bool:
        try:
            await self.client.collection("processed_messages").document(str(event_id)).create({
                "created_at": datetime.datetime.now(datetime.timezone.utc),
                "status": "processing"
            })
            return True
        except AlreadyExists:
            return False
        except Exception:
            return False

    async def create_game_record(self, game_state: GameState):
        data = game_state.model_dump(exclude={"id"}) 
        await self.client.collection("games").document(game_state.id).set(data)

    async def add_player_to_game(self, game_id: str, player: Player):
        await self.client.collection("games").document(game_id).update({
            "players": ArrayUnion([player.model_dump()])
        })
        
    async def set_game_active(self, game_id: str):
        await self.client.collection("games").document(game_id).update({
            "status": "active",
            "started_at": datetime.datetime.now(datetime.timezone.utc)
        })

    async def update_game_interface(self, game_id: str, interface: GameInterface):
        await self.client.collection("games").document(game_id).update({
            "interface": interface.model_dump()
        })

    async def get_game_by_channel_id(self, channel_id: str) -> GameState | None:
        try:
            games_ref = self.client.collection("games")
            query = games_ref.where("interface.listener_ids", "array_contains", str(channel_id)).limit(1)
            async for doc in query.stream():
                data = doc.to_dict()
                data['id'] = doc.id
                return GameState(**data)
            return None
        except Exception as e:
            logging.error(f"Persistence Error: {e}")
            return None

    async def get_game_by_id(self, game_id: str) -> GameState | None:
        try:
            doc = await self.client.collection("games").document(game_id).get()
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                return GameState(**data)
            return None
        except Exception:
            return None
            
    async def get_active_game_channels(self) -> set:
        active_ids = set()
        try:
            query = self.client.collection("games").where("status", "in", ["active", "setup"])
            async for doc in query.stream():
                data = doc.to_dict()
                interface = data.get('interface', {})
                listeners = interface.get('listener_ids', [])
                for cid in listeners:
                    active_ids.add(str(cid))
            return active_ids
        except Exception:
            return set()

    async def mark_game_ended(self, game_id: str):
        await self.client.collection("games").document(game_id).update({
            "status": "ended",
            "ended_at": datetime.datetime.now(datetime.timezone.utc)
        })

    async def update_game_metadata(self, game_id: str, metadata: dict):
        await self.client.collection("games").document(game_id).update({
            "metadata": metadata
        })

    # --- NEW: Patch Handler ---
    async def update_game_metadata_fields(self, game_id: str, patch: dict):
        """
        Updates specific fields in the metadata.
        Patch keys should be relative to metadata, e.g., 'oxygen' or 'players.ben.role'.
        We transform them to 'metadata.oxygen' for Firestore.
        """
        try:
            # Transform keys to target the metadata map
            firestore_update = {}
            for key, value in patch.items():
                firestore_update[f"metadata.{key}"] = value
                
            await self.client.collection("games").document(game_id).update(firestore_update)
        except Exception as e:
            logging.error(f"Persistence Error Patching Metadata: {e}")
            raise e

db = GameDatabase()
