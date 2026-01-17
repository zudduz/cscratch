import os
import logging
import asyncio
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, SystemMessage
from . import persistence

# PRICING (Gemini 1.5 Flash - Approx)
# Input: $0.075 per 1M
# Output: $0.30 per 1M

class AIEngine:
    def __init__(self):
        self.project_id = os.environ.get("GCP_PROJECT_ID")
        self.location = "us-central1"
        self.model = ChatVertexAI(
            model_name="gemini-1.5-flash-001",
            project=self.project_id,
            location=self.location,
            temperature=0.7,
            max_output_tokens=1024,
        )

    async def generate_response(self, system_prompt: str, conversation_id: str, user_input: str, model_version: str = "gemini-1.5-flash") -> str:
        try:
            # Construct Messages
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_input)
            ]
            
            # Invoke
            # Note: LangChain handles memory/history differently, but for this stateless agent approach
            # we just pass the raw context every time.
            result = await self.model.ainvoke(messages)
            
            # --- COST TRACKING ---
            # Fire-and-forget update to Firestore. Don't block the game loop.
            asyncio.create_task(self._track_usage(conversation_id, result.response_metadata))
            
            return result.content
            
        except Exception as e:
            logging.error(f"AI Generation Error: {e}")
            return f"[SYSTEM ERROR] Neural Link Severed: {e}"

    async def _track_usage(self, conversation_id: str, metadata: dict):
        try:
            # Extract Game ID (Format: "{game_id}_{actor_id}")
            if "_" not in conversation_id: return
            game_id = conversation_id.split("_")[0]
            
            usage = metadata.get('usage_metadata', {})
            in_tokens = usage.get('prompt_token_count', 0)
            out_tokens = usage.get('candidates_token_count', 0) # Gemini specific key
            
            # Fallback for standard LangChain keys if they change
            if in_tokens == 0: in_tokens = usage.get('input_tokens', 0)
            if out_tokens == 0: out_tokens = usage.get('output_tokens', 0)
            
            if in_tokens + out_tokens > 0:
                await persistence.db.increment_token_usage(game_id, in_tokens, out_tokens)
                
        except Exception as e:
            logging.warning(f"Failed to track usage: {e}")

ai = AIEngine()
