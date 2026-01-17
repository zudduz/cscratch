import os
import logging
import asyncio
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, SystemMessage
from . import persistence

# PRICING (Gemini 3 Flash Preview)
# Input: $0.50 per 1M
# Output: $3.00 per 1M

class AIEngine:
    def __init__(self):
        self.project_id = os.environ.get("GCP_PROJECT_ID")
        self.location = "us-central1"
        # Default to the bleeding edge
        self.default_model_name = "gemini-3-flash-preview"
        
        self.base_config = {
            "project": self.project_id,
            "location": self.location,
            "temperature": 0.7,
            "max_output_tokens": 1024,
        }
        
        # Initialize default client
        self.model = ChatVertexAI(model_name=self.default_model_name, **self.base_config)

    async def generate_response(self, system_prompt: str, conversation_id: str, user_input: str, model_version: str = "gemini-3-flash-preview") -> str:
        try:
            # Construct Messages
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_input)
            ]
            
            # Dynamic Model Selection
            # If the cartridge asks for an older model, we try to honor it, 
            # but default to Gemini 3 if unspecified or matching default.
            client = self.model
            if model_version and model_version != self.model.model_name:
                # Fallback or specific override
                client = ChatVertexAI(model_name=model_version, **self.base_config)
            
            # Invoke
            result = await client.ainvoke(messages)
            
            # --- COST TRACKING ---
            asyncio.create_task(self._track_usage(conversation_id, result.response_metadata))
            
            return result.content
            
        except Exception as e:
            logging.error(f"AI Generation Error: {e}")
            return f"[SYSTEM ERROR] Neural Link Severed: {e}"

    async def _track_usage(self, conversation_id: str, metadata: dict):
        try:
            # Extract Game ID
            if "_" not in conversation_id: return
            game_id = conversation_id.split("_")[0]
            
            usage = metadata.get('usage_metadata', {})
            in_tokens = usage.get('prompt_token_count', 0)
            out_tokens = usage.get('candidates_token_count', 0) 
            
            if in_tokens == 0: in_tokens = usage.get('input_tokens', 0)
            if out_tokens == 0: out_tokens = usage.get('output_tokens', 0)
            
            if in_tokens + out_tokens > 0:
                await persistence.db.increment_token_usage(game_id, in_tokens, out_tokens)
                
        except Exception as e:
            logging.warning(f"Failed to track usage: {e}")

ai = AIEngine()
