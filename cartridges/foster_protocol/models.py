from typing import List, Dict, Optional, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from .board import GameConfig
# --- GAME SPECIFIC STATE ---

class ChargingStation(BaseModel):
    pending_deactivation: List[str] = Field(default_factory=list)

class Player(BaseModel):
    role: Literal["loyal", "saboteur"] = "loyal"
    alive: bool = True
    location_id: str = "stasis_bay"
    requested_sleep: bool = False
    nanny_channel_id: Optional[str] = None

    @property
    def ready_for_sleep(self) -> bool:
        return (not self.alive) or self.requested_sleep

class Drone(BaseModel):
    id: str                    
    name: Optional[str] = None
    foster_id: Optional[str] = None
    role: Literal["loyal", "saboteur"] = "loyal"
    model_version: str = "gemini-2.5-flash" 
    
    location_id: str = "stasis_bay"
    battery: int = 100        
    
    destroyed: bool = False
    system_prompt: str = "You are a helpful drone."
    
    long_term_memory: str = "System Online. Mission: Maintain Ship. Await Orders."
    night_chat_log: List[str] = Field(default_factory=list)
    
    inventory: List[str] = Field(default_factory=list)
    daily_memory: List[str] = Field(default_factory=list)

    @property
    def status(self) -> str:
        if self.destroyed:
            return "destroyed"
        if self.battery <= 0:
            return "offline"
        return "active"

    @property
    def can_talk(self) -> bool:
        return self.status == "active" and self.location_id == "stasis_bay"


class Caisson(BaseModel):
    version: str = "2.43"
    oxygen: int = GameConfig.INITIAL_OXYGEN
    
    initial_crew_size: int = 1
    
    fuel: int = GameConfig.INITIAL_FUEL
    
    # --- FINITE RESOURCES ---
    shuttle_bay_fuel: int = GameConfig.CAPACITY_SHUTTLE_BAY
    torpedo_bay_fuel: int = GameConfig.CAPACITY_TORPEDO_BAY
    
    cycle: int = 1
    phase: Literal["day", "night"] = "night"
    
    # RENAMED FROM 'bots' -> 'drones'
    drones: Dict[str, Drone] = Field(default_factory=dict)
    
    players: Dict[str, Player] = Field(default_factory=dict)
    station: ChargingStation = Field(default_factory=ChargingStation)
    daily_logs: List[str] = Field(default_factory=list)

    # Pydantic V2 Config
    model_config = ConfigDict(populate_by_name=True)

    @property
    def is_ready_for_day(self) -> bool:
        if self.oxygen <= 0:
            return True

        return all(p.ready_for_sleep for p in self.players.values())

    # TODO add method for siphoning fuel

    def consume_oxygen(self, amount: int):
        self.oxygen = max(0, self.oxygen - amount)

    def add_fuel(self, amount: int):
        self.fuel = min(GameConfig.MAX_FUEL, self.fuel + amount)
