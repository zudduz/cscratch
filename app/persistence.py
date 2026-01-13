import datetime
import logging
from google.cloud.firestore import AsyncClient, ArrayUnion
from google.api_core.exceptions import AlreadyExists
from .models import GameState, Player, GameInterface

class GameDatabase:
    def __init__(self):
        self.client = AsyncClient(database="sandbox")

    async def lock_event(self, event_id: str) -> bool:
        try:
            await self.client.collection("processed_messages").document(str(event_id)).create({
                "created_at": datetime.datetime.now(datetime.timezone.utc),
                "status": "processing"
            })
            return True
        except AlreadyExists:
            return False
        except Exception as e:
            logging.error(f"Persistence Error locking event: {e}")
            return False

    async def create_game_record(self, game_state: GameState):
        try:
            data = game_state.model_dump(exclude={"id"}) 
            await self.client.collection("games").document(game_state.id).set(data)
        except Exception as e:
            logging.error(f"Persistence Error creating game: {e}")
            raise e

    async def add_player_to_game(self, game_id: str, player: Player):
        try:
            await self.client.collection("games").document(game_id).update({
                "players": ArrayUnion([player.model_dump()])
            })
        except Exception as e:
            logging.error(f"Persistence Error adding player: {e}")
            raise e

    async def set_game_active(self, game_id: str):
        try:
            await self.client.collection("games").document(game_id).update({
                "status": "active",
                "started_at": datetime.datetime.now(datetime.timezone.utc)
            })
        except Exception as e:
            logging.error(f"Persistence Error starting game: {e}")
            raise e

    async def update_game_metadata(self, game_id: str, metadata: dict):
        try:
            await self.client.collection("games").document(game_id).update({
                "metadata": metadata
            })
        except Exception as e:
            logging.error(f"Persistence Error updating metadata: {e}")
            raise e

    async def update_game_interface(self, game_id: str, interface: GameInterface):
        try:
            await self.client.collection("games").document(game_id).update({
                "interface": interface.model_dump()
            })
        except Exception as e:
            logging.error(f"Persistence Error updating interface: {e}")
            raise e

    # --- UPDATED LOOKUP ---
    async def get_game_by_channel_id(self, channel_id: str) -> GameState | None:
        try:
            games_ref = self.client.collection("games")
            
            # 1. Try new multi-channel lookup
            query = games_ref.where("interface.listener_ids", "array_contains", str(channel_id)).limit(1)
            async for doc in query.stream():
                data = doc.to_dict()
                data['id'] = doc.id
                return GameState(**data)
            
            # 2. Fallback to legacy single-channel lookup (for old games/lobbies)
            query_legacy = games_ref.where("interface.channel_id", "==", str(channel_id)).limit(1)
            async for doc in query_legacy.stream():
                data = doc.to_dict()
                data['id'] = doc.id
                return GameState(**data)
                
            return None
        except Exception as e:
            logging.error(f"Persistence Error finding game: {e}")
            return None

    async def get_game_by_id(self, game_id: str) -> GameState | None:
        try:
            doc = await self.client.collection("games").document(game_id).get()
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                return GameState(**data)
            return None
        except Exception as e:
            logging.error(f"Persistence Error finding game by id: {e}")
            return None

    async def mark_game_ended(self, game_id: str):
        try:
            await self.client.collection("games").document(game_id).update({
                "status": "ended",
                "ended_at": datetime.datetime.now(datetime.timezone.utc)
            })
        except Exception as e:
            logging.error(f"Persistence Error ending game: {e}")
            raise e

    async def get_active_game_channels(self) -> set:
        active_ids = set()
        try:
            query = self.client.collection("games").where("status", "in", ["active", "setup"])
            async for doc in query.stream():
                data = doc.to_dict()
                interface = data.get('interface', {})
                
                # Collect ALL known channel IDs
                
                # 1. Legacy
                legacy_id = interface.get('channel_id')
                if legacy_id: active_ids.add(str(legacy_id))
                
                # 2. Multi-channel
                listeners = interface.get('listener_ids', [])
                for cid in listeners:
                    active_ids.add(str(cid))
                    
            return active_ids
        except Exception as e:
            logging.error(f"Persistence Error hydrating cache: {e}")
            return set()

db = GameDatabase()
