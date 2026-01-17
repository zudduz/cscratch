import os
import logging
import asyncio
from google.cloud import firestore
from .models import GameState

class PersistenceLayer:
    def __init__(self):
        self.db = firestore.AsyncClient(database="sandbox")
        self.games_collection = self.db.collection('games')

    async def get_game_by_id(self, game_id: str) -> GameState:
        doc = await self.games_collection.document(game_id).get()
        if doc.exists:
            return GameState(**doc.to_dict())
        return None

    async def save_game(self, game: GameState):
        await self.games_collection.document(game.id).set(game.model_dump())

    async def update_game_interface(self, game_id: str, interface):
        await self.games_collection.document(game_id).update({
            "interface": interface.model_dump()
        })

    # --- ATOMIC INCREMENT FOR TOKENS ---
    async def increment_token_usage(self, game_id: str, input_tokens: int, output_tokens: int):
        ref = self.games_collection.document(game_id)
        # Firestore 'Increment' is atomic. Safe for parallel bots.
        await ref.update({
            "usage_input_tokens": firestore.Increment(input_tokens),
            "usage_output_tokens": firestore.Increment(output_tokens)
        })

    async def get_active_game_channels(self):
        # Scan for active games to rehydrate listeners on bot restart
        active_channels = set()
        # Query: status != 'ended' (Requires composite index, so we'll just scan recent or filter in app for now to keep it simple)
        # For simplicity in this prototype, we'll scan all. In prod, add an index.
        async for doc in self.games_collection.stream():
            data = doc.to_dict()
            if data.get('status') == 'active':
                interface = data.get('interface', {})
                # Add main channel
                if interface.get('main_channel_id'):
                    active_channels.add(str(interface['main_channel_id']))
                # Add sub channels
                for cid in interface.get('channels', {}).values():
                    active_channels.add(str(cid))
        return active_channels

    # Basic Redis-like Lock using Firestore (Simulated for this context)
    async def lock_event(self, event_id: str) -> bool:
        # Prevent double-processing of Discord webhooks/events
        # In a real app, use Redis. Here we'll just return True for dev.
        return True 

db = PersistenceLayer()
