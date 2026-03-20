from datetime import datetime, timezone
from typing import List, Dict, Optional, Any, Literal
from pydantic import BaseModel, Field, ConfigDict

# --- Discord Models ---
class LobbyPlayer(BaseModel):
    id: str
    name: str

class GameInterface(BaseModel):
    type: str = "discord"
    guild_id: Optional[str] = None
    category_id: Optional[str] = None
    
    main_channel_id: Optional[str] = None 
    channels: Dict[str, str] = Field(default_factory=dict)
    listener_ids: List[str] = Field(default_factory=list)
    
    channel_id: Optional[str] = None

class GameState(BaseModel):
    id: str
    story_id: str
    host_id: str
    status: str 
    created_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    metadata: Dict[str, Any] = {}
    players: List[LobbyPlayer] = []
    interface: GameInterface = Field(default_factory=GameInterface)
    schema_version: int = 2
    
    # Versioning for optimistic concurrency
    version: int = Field(default=1, description="Sequence number for state updates")
    
    # --- COST TRACKING ---
    usage_input_tokens: int = 0
    usage_output_tokens: int = 0

    # Pydantic V2 Config
    model_config = ConfigDict(populate_by_name=True)

class AILogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    game_id: str
    model: str
    system_prompt: str
    user_input: str
    raw_response: str
    usage: Dict[str, Any] = Field(default_factory=dict)

class User(BaseModel):
    """
    Global user entity for cross-game progression (Economy, Stats).
    Stored in 'users' collection in Firestore.
    """
    id: str
    scratch_balance: int = 0