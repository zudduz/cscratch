from datetime import datetime
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

class Player(BaseModel):
    id: str
    name: str
    joined_at: str

class GameInterface(BaseModel):
    type: str = "discord"
    guild_id: Optional[str] = None
    category_id: Optional[str] = None
    
    # NEW: Multi-channel support
    # The primary channel (e.g. #picnic)
    main_channel_id: Optional[str] = None 
    
    # Map of logical names to IDs: {'picnic': '123', 'nanny_userA': '456'}
    channels: Dict[str, str] = Field(default_factory=dict)
    
    # Flattened list of ALL IDs for Firestore 'array-contains' queries
    listener_ids: List[str] = Field(default_factory=list)
    
    # Legacy field (optional, for backward compatibility during migration)
    channel_id: Optional[str] = None

class GameState(BaseModel):
    id: str
    story_id: str
    status: str  # 'setup', 'active', 'ended'
    created_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    metadata: Dict[str, Any] = {}
    players: List[Player] = []
    interface: GameInterface = Field(default_factory=GameInterface)
    schema_version: int = 2

    class Config:
        populate_by_name = True
