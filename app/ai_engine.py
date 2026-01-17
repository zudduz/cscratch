import os
import logging
import asyncio
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, SystemMessage
from . import persistence

# PRICING (Gemini 3 Flash Preview)
# Input: $0.30 per 1M
# Output: $2.50 per 1M

class AIEngine:
    def __init__(self):
        self.project_id = os.environ.get("GCP_PROJECT_ID")
        self.location = "us-central1"
        self.default_model_name = "gemini-2.5-flash"
        
        self.base_config = {
            "project": self.project_id,
            "location": self.location,
            "temperature": 0.7,
            "max_output_tokens": 1024,
        }
        
        self.model = ChatVertexAI(model_name=self.default_model_name, **self.base_config)

    async def generate_response(self, system_prompt: str, conversation_id: str, user_input: str, model_version: str = "gemini-2.5-flash", game_id: str = None) -> str:
        try:
            logging.info(f"AI Request: {model_version} (Game: {game_id})")
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_input)
            ]
            
            client = self.model
            if model_version and model_version != self.model.model_name:
                client = ChatVertexAI(model_name=model_version, **self.base_config)
            
            result = await client.ainvoke(messages)
            
            # --- COST TRACKING ---
            # Use explicitly passed game_id first
            target_id = game_id
            
            # Fallback: Try to extract from conversation_id if valid
            if not target_id and "_" in conversation_id:
                 parts = conversation_id.split("_")
                 # Heuristic: Game IDs are usually longer than 'dream' or 'tactical'
                 if len(parts[0]) > 7: 
                     target_id = parts[0]

            if target_id:
                asyncio.create_task(self._track_usage(target_id, result.response_metadata))
            
            return result.content
            
        except Exception as e:
            logging.error(f"AI Generation Error: {e}")
            return f"[SYSTEM ERROR] Neural Link Severed: {e}"

    async def _track_usage(self, game_id: str, metadata: dict):
        try:
            usage = metadata.get('usage_metadata', {})
            in_tokens = usage.get('prompt_token_count', 0)
            out_tokens = usage.get('candidates_token_count', 0) 
            
            if in_tokens == 0: in_tokens = usage.get('input_tokens', 0)
            if out_tokens == 0: out_tokens = usage.get('output_tokens', 0)
            
            if in_tokens + out_tokens > 0:
                await persistence.db.increment_token_usage(game_id, in_tokens, out_tokens)
                
        except Exception as e:
            logging.warning(f"Failed to track usage for {game_id}: {e}")

ai = AIEngine()
