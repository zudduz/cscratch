import os
import logging
import asyncio
import warnings
from langchain_core._api.deprecation import LangChainDeprecationWarning
from models import AILogEntry

# SUPPRESS FALSE POSITIVE WARNING:
# LangChain recommends switching to ChatGoogleGenerativeAI, but that requires an API Key.
# We are on Cloud Run (Vertex AI) using Service Account Auth, so we MUST use ChatVertexAI.
warnings.filterwarnings("ignore", category=LangChainDeprecationWarning)

from langchain_google_vertexai import ChatVertexAI, HarmBlockThreshold, HarmCategory
from langchain_core.messages import HumanMessage, SystemMessage
from . import persistence

# PRICING (Gemini 2.5 Flash)
# Input: $0.30 per 1M ($0.075 Cached)
# Output: $1.25 per 1M

# --- SHARED AUTH STATE ---
# We keep the model instance global so it reuses the underlying 
# connection pool and cached OAuth tokens across parallel games.
_SHARED_MODEL = None
_MODEL_LOCK = asyncio.Lock()

def _sanitize_schema(schema: dict) -> dict:
    """
    Recursively removes 'additionalProperties' and 'title' from the schema 
    to make it compatible with Vertex AI Controlled Generation.
    """
    if isinstance(schema, dict):
        return {
            k: _sanitize_schema(v) 
            for k, v in schema.items() 
            if k not in ["additionalProperties", "title"]
        }
    elif isinstance(schema, list):
        return [_sanitize_schema(v) for v in schema]
    else:
        return schema

class AIEngine:
    def __init__(self):
        # Default to sandbox ID but allow env override
        self.project_id = os.environ.get("GCP_PROJECT_ID", "sandbox-456821")
        self.location = "us-central1"
        self.default_model_name = "gemini-2.5-flash"
        
        # PERMISSIVE SAFETY SETTINGS (Required for Horror/Survival themes)
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        self.base_config = {
            "project": self.project_id,
            "location": self.location,
            "temperature": 0.7,
            "max_output_tokens": 8192,
            "safety_settings": self.safety_settings,
        }

    async def _get_model(self, model_name: str):
        """Ensures a single instance of the model is shared across the app."""
        global _SHARED_MODEL
        async with _MODEL_LOCK:
            if _SHARED_MODEL is None or _SHARED_MODEL.model_name != model_name:
                logging.info(f"System: Initializing Shared AI Session ({model_name})")
                _SHARED_MODEL = ChatVertexAI(model_name=model_name, **self.base_config)
            return _SHARED_MODEL

    async def generate_response(
        self, 
        system_prompt: str, 
        conversation_id: str, 
        user_input: str, 
        model_version: str = "gemini-2.5-flash", 
        game_id: str = None,
        response_schema: dict = None
    ) -> str:
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_input)
            ]
            
            # Reuse the shared model/connection pool for Auth caching
            model = await self._get_model(model_version)
            
            # Restore your instrumentation logic
            target_id = game_id
            if not target_id and "_" in conversation_id:
                parts = conversation_id.split("_")
                if len(parts[0]) > 7:
                    target_id = parts[0]
            
            if target_id:
                logging.info(f"AI Request: {model.model_name} (Game: {target_id})")
            
            # --- STRUCTURED OUTPUT BINDING ---
            # If a schema is provided, we bind it to the model for this specific invocation.
            # This enables "Controlled Generation" (JSON Mode) on Vertex AI.
            if response_schema:
                response_schema = _sanitize_schema(response_schema)
                invocation_model = model.bind(
                    response_mime_type="application/json",
                    response_schema=response_schema
                )
            else:
                invocation_model = model

            result = await invocation_model.ainvoke(messages)
            
            if target_id:
                log_entry = AILogEntry(
                    game_id=target_id,
                    model=model.model_name,
                    system_prompt=system_prompt,
                    user_input=user_input,
                    raw_response=result.content,
                    usage=result.response_metadata.get('usage_metadata', {})
                )
                asyncio.create_task(persistence.db.log_ai_interaction(log_entry))            

            metadata = result.response_metadata
            finish_reason = metadata.get('finish_reason')
            
            if not result.content:
                logging.error(f"[AI SAFETY BLOCK] Content is empty. Finish Reason: {finish_reason}")
                logging.error(f"[AI SAFETY DATA] Ratings: {metadata.get('safety_ratings')}")
                return ""

            if finish_reason and finish_reason != "STOP":
                logging.error(f"[AI TRUNCATION] Stop Reason: {finish_reason} (Game: {target_id})")

            if target_id:
                asyncio.create_task(self._track_usage(target_id, result.response_metadata))
            
            return result.content
            
        except Exception as e:
            logging.error(f"AI Generation Error: {e}")
            return f"[SYSTEM ERROR]: {e}"

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