from pydantic import BaseModel, Field
from typing import List, Dict, Literal, Optional

# --- SUB-SYSTEMS ---
class ChargingStation(BaseModel):
    # The "Death Row"
    # If a Bot ID is in this list, they are killed immediately upon docking.
    pending_deactivation: List[str] = Field(default_factory=list)
    
    # We could track charging efficiency here later
    charge_rate: int = 10 

# --- THE CREW (PLAYERS) ---
class PlayerState(BaseModel):
    role: Literal["loyal", "saboteur"] = "loyal"
    is_alive: bool = True
    location_id: str = "cryo_bay"

# --- THE TOOLS (BOTS) ---
class BotState(BaseModel):
    id: str                 
    location_id: str = "cryo_bay"
    
    # Resources
    battery: int = 100      
    action_points: int = 10 
    
    # Status
    status: Literal["active", "destroyed"] = "active"
    
    # Personality
    system_prompt: str = "You are a helpful drone."
    goal_summary: str = "Maintain the ship."
    
    # Inventory
    inventory: List[str] = Field(default_factory=list)
    
    # Mechanics
    towing_id: Optional[str] = None

# --- THE WORLD (ROOT) ---
class CaissonState(BaseModel):
    version: str = "1.2"
    
    # Global Resources
    oxygen: int = 100
    fuel: int = 0
    
    # Time
    cycle: int = 1
    phase: Literal["day", "night"] = "night"
    
    # Entities
    bots: Dict[str, BotState] = Field(default_factory=dict)
    players: Dict[str, PlayerState] = Field(default_factory=dict)
    
    # Facilities
    station: ChargingStation = Field(default_factory=ChargingStation)
    
    # Public Event Log
    daily_logs: List[str] = Field(default_factory=list)

    def consume_oxygen(self, amount: int):
        self.oxygen = max(0, self.oxygen - amount)

    def add_fuel(self, amount: int):
        self.fuel = min(100, self.fuel + amount)
