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
    channel_id: Optional[str] = None
    category_id: Optional[str] = None

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
        # Allows populating by field name (useful for Firestore)
        populate_by_name = True
