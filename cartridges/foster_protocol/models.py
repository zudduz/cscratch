from pydantic import BaseModel, Field
from typing import List, Dict, Literal, Optional

class ChargingStation(BaseModel):
    pending_deactivation: List[str] = Field(default_factory=list)
    charge_rate: int = 10 

class PlayerState(BaseModel):
    role: Literal["loyal", "saboteur"] = "loyal"
    is_alive: bool = True
    location_id: str = "cryo_bay"
    is_sleeping: bool = False
    nanny_channel_id: Optional[str] = None

class BotState(BaseModel):
    id: str                 
    foster_id: Optional[str] = None
    role: Literal["loyal", "saboteur"] = "loyal"
    model_version: str = "gemini-2.5-flash" 
    
    location_id: str = "cryo_bay"
    battery: int = 100      
    last_battery_drop: int = 0
    action_points: int = 10 
    status: Literal["active", "destroyed"] = "active"
    
    system_prompt: str = "You are a helpful drone."
    goal_summary: str = "Maintain the ship."
    inventory: List[str] = Field(default_factory=list)
    
    # NEW: Private memory of the day's events
    daily_memory: List[str] = Field(default_factory=list)

class CaissonState(BaseModel):
    version: str = "2.0"
    oxygen: int = 100
    last_oxygen_drop: int = 0
    fuel: int = 0
    last_fuel_gain: int = 0
    cycle: int = 1
    phase: Literal["day", "night"] = "night"
    
    bots: Dict[str, BotState] = Field(default_factory=dict)
    players: Dict[str, PlayerState] = Field(default_factory=dict)
    station: ChargingStation = Field(default_factory=ChargingStation)
    
    # Global log for the Mainframe
    daily_logs: List[str] = Field(default_factory=list)

    def consume_oxygen(self, amount: int):
        self.oxygen = max(0, self.oxygen - amount)

    def add_fuel(self, amount: int):
        self.fuel = min(100, self.fuel + amount)
