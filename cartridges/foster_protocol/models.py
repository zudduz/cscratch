from pydantic import BaseModel, Field
from typing import List, Dict, Literal, Optional

# --- THE CREW (PLAYERS) ---
class PlayerState(BaseModel):
    # Default is loyal. Saboteur is assigned at game start.
    role: Literal["loyal", "saboteur"] = "loyal"
    
    # Life State
    is_alive: bool = True
    location_id: str = "cryo_bay" # Players are stuck in pods, but good to track

# --- THE TOOLS (BOTS) ---
class BotState(BaseModel):
    id: str                 # "unit_734"
    location_id: str = "cryo_bay"
    
    # Resources
    battery: int = 100      # 0 = Unconscious
    action_points: int = 10 # Refreshes daily
    
    # Status
    # 'active' = Normal
    # 'destroyed' = Permanently dead (e.g. crushed)
    status: Literal["active", "destroyed"] = "active"
    
    # Personality / AI Context
    system_prompt: str = "You are a helpful drone."
    goal_summary: str = "Maintain the ship."
    
    # Inventory
    inventory: List[str] = Field(default_factory=list)
    
    # Mechanics
    # If set, this bot is dragging another bot (costing extra AP)
    towing_id: Optional[str] = None

# --- THE WORLD (ROOT) ---
class CaissonState(BaseModel):
    version: str = "1.1" # Schema Version
    
    # Global Resources
    oxygen: int = 100
    fuel: int = 0
    
    # Time
    cycle: int = 1
    phase: Literal["day", "night"] = "night"
    
    # Entities
    bots: Dict[str, BotState] = Field(default_factory=dict)
    players: Dict[str, PlayerState] = Field(default_factory=dict)
    
    # Public Event Log
    daily_logs: List[str] = Field(default_factory=list)

    def consume_oxygen(self, amount: int):
        self.oxygen = max(0, self.oxygen - amount)

    def add_fuel(self, amount: int):
        self.fuel = min(100, self.fuel + amount)
