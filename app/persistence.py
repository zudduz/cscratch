import os
import logging
import asyncio
from google.cloud import firestore
from .models import GameState, AILogEntry, LobbyPlayer, User

class PersistenceLayer:
    def __init__(self):
        # Explicitly use the 'sandbox' database to match existing data
        self.db = firestore.AsyncClient(database="sandbox")
        self.games_collection = self.db.collection('games')
        self.channels_collection = self.db.collection('channels')
        self.users_collection = self.db.collection('users')

    async def create_game_record(self, game: GameState):
        await self.games_collection.document(game.id).set(game.model_dump())

    async def get_game_by_id(self, game_id: str) -> GameState:
        doc = await self.games_collection.document(game_id).get()
        if doc.exists:
            return GameState(**doc.to_dict())
        return None

    async def add_player_to_game(self, game_id: str, player: LobbyPlayer):
        """
        Uses firestore.ArrayUnion to atomically append a player.
        Safe from race conditions without a transaction.
        Increments version to signal state change.
        """
        try:
            game_ref = self.games_collection.document(game_id)
            await game_ref.update({
                "players": firestore.ArrayUnion([player.model_dump()]),
                "version": firestore.Increment(1)
            })
            return True
        except Exception as e:
            logging.error(f"Failed to add player via ArrayUnion: {e}")
            return False

    async def update_game_interface(self, game_id: str, interface):
        await self.games_collection.document(game_id).update({
            "interface": interface.model_dump(),
            "version": firestore.Increment(1)
        })

    async def update_game_metadata(self, game_id: str, metadata: dict, expected_version: int):
        """
        Replaces the entire metadata field using a transaction to verify version.
        """
        transaction = self.db.transaction()
        game_ref = self.games_collection.document(game_id)

        @firestore.async_transactional
        async def _update_with_version(transaction, game_ref, new_metadata, version):
            snapshot = await game_ref.get(transaction=transaction)
            if not snapshot.exists:
                return False
            
            current_version = snapshot.to_dict().get("version", 1)
            if current_version != version:
                logging.warning(f"Version mismatch for {game_id}: expected {version}, found {current_version}")
                return False
            
            transaction.update(game_ref, {
                "metadata": new_metadata,
                "version": firestore.Increment(1)
            })
            return True

        try:
            return await _update_with_version(transaction, game_ref, metadata, expected_version)
        except Exception as e:
            logging.error(f"Transaction failed for update_game_metadata: {e}")
            return False

    async def update_game_metadata_fields(self, game_id: str, patch: dict):
        """Targeted update using dot-notation for nested fields."""
        update_dict = {"version": firestore.Increment(1)}
        for key, value in patch.items():
            update_dict[f"metadata.{key}"] = value
        
        await self.games_collection.document(game_id).update(update_dict)

    async def set_game_active(self, game_id: str):
        await self.games_collection.document(game_id).update({
            "status": "active", 
            "started_at": firestore.SERVER_TIMESTAMP,
            "version": firestore.Increment(1)
        })

    async def mark_game_ended(self, game_id: str):
        await self.games_collection.document(game_id).update({
            "status": "ended",
            "ended_at": firestore.SERVER_TIMESTAMP,
            "version": firestore.Increment(1)
        })

    async def increment_token_usage(self, game_id: str, input_tokens: int, output_tokens: int):
        """Atomic server-side increment for usage tracking."""
        ref = self.games_collection.document(game_id)
        await ref.update({
            "usage_input_tokens": firestore.Increment(input_tokens),
            "usage_output_tokens": firestore.Increment(output_tokens)
        })

    async def get_active_game_channels(self):
        active_map = {}
        async for doc in self.games_collection.stream():
            data = doc.to_dict()
            if data.get('status') == 'active':
                g_id = data.get('id')
                interface = data.get('interface', {})
                
                if interface.get('main_channel_id'):
                    active_map[str(interface['main_channel_id'])] = g_id
                
                for cid in interface.get('channels', {}).values():
                    active_map[str(cid)] = g_id
        return active_map

    async def register_channel_association(self, channel_id: str, game_id: str):
        try:
            await self.channels_collection.document(str(channel_id)).set({"game_id": game_id})
        except Exception as e:
            logging.error(f"Failed to register channel index: {e}")

    async def remove_channel_association(self, channel_id: str):
        try:
            await self.channels_collection.document(str(channel_id)).delete()
        except Exception as e:
            logging.warning(f"Failed to remove channel index: {e}")

    async def get_game_id_by_channel_index(self, channel_id: str) -> str:
        doc = await self.channels_collection.document(str(channel_id)).get()
        if doc.exists:
            return doc.to_dict().get("game_id")
        return None

    async def lock_event(self, event_id: str) -> bool:
        return True 

    async def log_ai_interaction(self, entry: AILogEntry):
        await self.games_collection.document(entry.game_id).collection('logs').add(entry.model_dump())

    async def get_game_logs(self, game_id: str, limit: int = 50):
        logs = []
        ref = self.games_collection.document(game_id).collection('logs')
        async for doc in ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit).stream():
            logs.append(doc.to_dict())
        return logs

    # --- ECONOMY / SCRATCH ---

    async def get_user(self, user_id: str) -> User:
        """Fetches a full User object. Returns None if not found."""
        doc = await self.users_collection.document(str(user_id)).get()
        if doc.exists:
            # Inject ID if missing from doc body (common pattern in Firestore)
            data = doc.to_dict()
            if "id" not in data:
                data["id"] = doc.id
            return User(**data)
        return None

    async def get_user_balance(self, user_id: str) -> int:
        """Lightweight helper to get just the balance."""
        doc = await self.users_collection.document(str(user_id)).get()
        if doc.exists:
            return doc.to_dict().get("scratch_balance", 0)
        return 0

    async def adjust_user_balance(self, user_id: str, amount: int) -> int:
        """
        Transactional update.
        If user exists: Increments balance.
        If user new: Creates full User object (with defaults) and sets initial balance.
        """
        transaction = self.db.transaction()
        ref = self.users_collection.document(str(user_id))

        @firestore.async_transactional
        async def _adjust_txn(transaction, ref):
            snapshot = await ref.get(transaction=transaction)
            
            if snapshot.exists:
                current_bal = snapshot.to_dict().get("scratch_balance", 0)
                new_bal = current_bal + amount
                transaction.update(ref, {"scratch_balance": new_bal})
                return new_bal
            else:
                # User doesn't exist; use Pydantic to ensure schema compliance
                # Default balance is 0, so we initialize with amount
                new_user = User(id=user_id, scratch_balance=amount)
                transaction.set(ref, new_user.model_dump())
                return amount

        return await _adjust_txn(transaction, ref)

db = PersistenceLayer()