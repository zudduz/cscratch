from datetime import datetime
from typing import List, Dict, Optional, Any, Literal
from pydantic import BaseModel, Field

# --- Discord Models ---
class Player(BaseModel):
    id: str
    name: str
    joined_at: str

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
    players: List[Player] = []
    interface: GameInterface = Field(default_factory=GameInterface)
    schema_version: int = 2
    
    # --- COST TRACKING ---
    usage_input_tokens: int = 0
    usage_output_tokens: int = 0

    class Config:
        populate_by_name = True
