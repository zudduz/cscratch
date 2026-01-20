from typing import List, Dict, Optional, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from .board import GameConfig

# --- GAME SPECIFIC STATE ---

class ChargingStation(BaseModel):
    pending_deactivation: List[str] = Field(default_factory=list)
    charge_rate: int = 100 

class PlayerState(BaseModel):
    role: Literal["loyal", "saboteur"] = "loyal"
    is_alive: bool = True
    location_id: str = "stasis_bay"
    is_sleeping: bool = False
    nanny_channel_id: Optional[str] = None

class DroneState(BaseModel):
    id: str                   
    name: Optional[str] = None
    foster_id: Optional[str] = None
    role: Literal["loyal", "saboteur"] = "loyal"
    model_version: str = "gemini-2.5-flash" 
    
    location_id: str = "stasis_bay"
    battery: int = 100        
    last_battery_drop: int = 0
    
    status: Literal["active", "destroyed"] = "active"
    system_prompt: str = "You are a helpful drone."
    
    long_term_memory: str = "I have just come online. I must find my Foster Parent."
    night_chat_log: List[str] = Field(default_factory=list)
    
    inventory: List[str] = Field(default_factory=list)
    daily_memory: List[str] = Field(default_factory=list)

class CaissonState(BaseModel):
    version: str = "2.42"
    oxygen: int = GameConfig.INITIAL_OXYGEN
    last_oxygen_drop: int = 0
    emergency_power: bool = False 
    
    initial_crew_size: int = 1
    
    fuel: int = GameConfig.INITIAL_FUEL
    last_fuel_gain: int = 0
    
    # --- FINITE RESOURCES ---
    shuttle_bay_fuel: int = GameConfig.CAPACITY_SHUTTLE_BAY
    torpedo_bay_fuel: int = GameConfig.CAPACITY_TORPEDO_BAY
    
    cycle: int = 1
    phase: Literal["day", "night"] = "night"
    
    # RENAMED FROM 'bots' -> 'drones'
    drones: Dict[str, DroneState] = Field(default_factory=dict)
    
    players: Dict[str, PlayerState] = Field(default_factory=dict)
    station: ChargingStation = Field(default_factory=ChargingStation)
    daily_logs: List[str] = Field(default_factory=list)

    # Pydantic V2 Config
    model_config = ConfigDict(populate_by_name=True)

    def consume_oxygen(self, amount: int):
        self.oxygen = max(0, self.oxygen - amount)

    def add_fuel(self, amount: int):
        self.fuel = min(GameConfig.MAX_FUEL, self.fuel + amount)
