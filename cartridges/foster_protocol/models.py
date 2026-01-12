from pydantic import BaseModel, Field
from typing import List, Dict, Literal, Optional

class BotState(BaseModel):
    id: str                 # "unit_734"
    location_id: str = "cryo_bay"
    battery: int = 100
    is_active: bool = True
    
    # Inventory: Simple list of item IDs (e.g. "fuel_canister", "plasma_torch")
    inventory: List[str] = Field(default_factory=list)
    
    # The Hidden Role (Assigned at runtime)
    role: Literal["loyal", "saboteur"] = "loyal"

class FosterState(BaseModel):
    # Global Resources
    oxygen: int = 100
    fuel: int = 0
    
    # Time
    cycle: int = 1
    phase: Literal["day", "night"] = "night"
    
    # Actors (Keyed by Bot ID)
    bots: Dict[str, BotState] = Field(default_factory=dict)
    
    # Public Event Log (For the "Morning Report")
    daily_logs: List[str] = Field(default_factory=list)

    def consume_oxygen(self, amount: int):
        self.oxygen = max(0, self.oxygen - amount)

    def add_fuel(self, amount: int):
        self.fuel = min(100, self.fuel + amount)
