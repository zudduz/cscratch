from pydantic import BaseModel, Field
from typing import List, Dict, Literal, Optional

# --- SUB-SYSTEMS ---
class ChargingStation(BaseModel):
    pending_deactivation: List[str] = Field(default_factory=list)
    charge_rate: int = 10 

# --- THE CREW (PLAYERS) ---
class PlayerState(BaseModel):
    role: Literal["loyal", "saboteur"] = "loyal"
    is_alive: bool = True
    location_id: str = "cryo_bay"
    is_sleeping: bool = False
    nanny_channel_id: Optional[str] = None

# --- THE TOOLS (BOTS) ---
class BotState(BaseModel):
    id: str                 
    foster_id: Optional[str] = None
    
    # HARDWARE SPECS (2026 Era)
    model_version: str = "gemini-2.5-flash" 
    
    location_id: str = "cryo_bay"
    battery: int = 100      
    last_battery_drop: int = 0
    action_points: int = 10 
    status: Literal["active", "destroyed"] = "active"
    
    system_prompt: str = "You are a helpful drone."
    goal_summary: str = "Maintain the ship."
    inventory: List[str] = Field(default_factory=list)
    towing_id: Optional[str] = None

# --- THE WORLD (ROOT) ---
class CaissonState(BaseModel):
    version: str = "1.8"
    oxygen: int = 100
    last_oxygen_drop: int = 0
    fuel: int = 0
    last_fuel_gain: int = 0
    cycle: int = 1
    phase: Literal["day", "night"] = "night"
    
    picnic_channel_id: Optional[str] = None
    
    bots: Dict[str, BotState] = Field(default_factory=dict)
    players: Dict[str, PlayerState] = Field(default_factory=dict)
    station: ChargingStation = Field(default_factory=ChargingStation)
    daily_logs: List[str] = Field(default_factory=list)

    def consume_oxygen(self, amount: int):
        self.oxygen = max(0, self.oxygen - amount)

    def add_fuel(self, amount: int):
        self.fuel = min(100, self.fuel + amount)
