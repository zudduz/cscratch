import os
import logging
import asyncio
from google.cloud import firestore
from .models import GameState

class PersistenceLayer:
    def __init__(self):
        # Explicitly use the 'sandbox' database to match existing data
        self.db = firestore.AsyncClient(database="sandbox")
        self.games_collection = self.db.collection('games')
        self.channels_collection = self.db.collection('channels')

    async def create_game_record(self, game: GameState):
        await self.games_collection.document(game.id).set(game.model_dump())

    async def get_game_by_id(self, game_id: str) -> GameState:
        doc = await self.games_collection.document(game_id).get()
        if doc.exists:
            return GameState(**doc.to_dict())
        return None

    async def get_game_by_channel_id(self, channel_id: str) -> GameState:
        # In a real app, use a composite index. 
        # For prototype, we scan. (Inefficient but functional for small scale)
        async for doc in self.games_collection.stream():
            data = doc.to_dict()
            interface = data.get('interface', {})
            
            # Check main channel
            if str(interface.get('main_channel_id')) == str(channel_id):
                return GameState(**data)
            
            # Check sub-channels
            if str(channel_id) in interface.get('channels', {}).values():
                return GameState(**data)
                
        return None

    async def add_player_to_game(self, game_id: str, player):
        game = await self.get_game_by_id(game_id)
        if game:
            # Check for duplicates
            if any(p.id == player.id for p in game.players):
                return
            game.players.append(player)
            await self.save_game(game)

    async def update_game_interface(self, game_id: str, interface):
        await self.games_collection.document(game_id).update({
            "interface": interface.model_dump()
        })

    async def update_game_metadata(self, game_id: str, metadata: dict):
        # Full replacement of metadata
        await self.games_collection.document(game_id).update({
            "metadata": metadata
        })

    async def update_game_metadata_fields(self, game_id: str, patch: dict):
        # Deep patch for dot notation (e.g., "bots.unit_123.battery": 90)
        # Firestore update() handles dot notation natively for nested fields
        update_dict = {}
        for key, value in patch.items():
            # Prefix with 'metadata.' to target the metadata field in the doc
            update_dict[f"metadata.{key}"] = value
        
        await self.games_collection.document(game_id).update(update_dict)

    async def set_game_active(self, game_id: str):
        await self.games_collection.document(game_id).update({
            "status": "active", 
            "started_at": firestore.SERVER_TIMESTAMP
        })

    async def mark_game_ended(self, game_id: str):
        await self.games_collection.document(game_id).update({
            "status": "ended",
            "ended_at": firestore.SERVER_TIMESTAMP
        })

    async def save_game(self, game: GameState):
        await self.games_collection.document(game.id).set(game.model_dump())

    # --- ATOMIC INCREMENT FOR TOKENS ---
    async def increment_token_usage(self, game_id: str, input_tokens: int, output_tokens: int):
        ref = self.games_collection.document(game_id)
        # Firestore 'Increment' is atomic. Safe for parallel bots.
        await ref.update({
            "usage_input_tokens": firestore.Increment(input_tokens),
            "usage_output_tokens": firestore.Increment(output_tokens)
        })

    async def get_active_game_channels(self):
        # This hydrates the in-memory cache on startup
        active_map = {}
        async for doc in self.games_collection.stream():
            data = doc.to_dict()
            if data.get('status') == 'active':
                g_id = data.get('id')
                interface = data.get('interface', {})
                
                # Add main channel
                if interface.get('main_channel_id'):
                    active_map[str(interface['main_channel_id'])] = g_id
                
                # Add sub channels
                for cid in interface.get('channels', {}).values():
                    active_map[str(cid)] = g_id
        return active_map

    async def register_channel_association(self, channel_id: str, game_id: str):
        """Write the O(1) index entry."""
        try:
            await self.channels_collection.document(str(channel_id)).set({"game_id": game_id})
        except Exception as e:
            logging.error(f"Failed to register channel index: {e}")

    async def remove_channel_association(self, channel_id: str):
        """Remove the index entry (Clean up)."""
        try:
            await self.channels_collection.document(str(channel_id)).delete()
        except Exception as e:
            logging.warning(f"Failed to remove channel index: {e}")

    async def get_game_id_by_channel_index(self, channel_id: str) -> str:
        """Fast O(1) Lookup."""
        doc = await self.channels_collection.document(str(channel_id)).get()
        if doc.exists:
            return doc.to_dict().get("game_id")
        return None

    # Basic Redis-like Lock using Firestore (Simulated for this context)
    async def lock_event(self, event_id: str) -> bool:
        # Prevent double-processing of Discord webhooks/events
        return True 

    async def log_ai_interaction(self, entry: AILogEntry):
        # Store in a subcollection 'logs' under the game document
        # This keeps it organized and scalable
        await self.games_collection.document(entry.game_id).collection('logs').add(entry.model_dump())

    async def get_game_logs(self, game_id: str, limit: int = 50):
        logs = []
        ref = self.games_collection.document(game_id).collection('logs')
        async for doc in ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit).stream():
            logs.append(doc.to_dict())
        return logs

db = PersistenceLayer()
