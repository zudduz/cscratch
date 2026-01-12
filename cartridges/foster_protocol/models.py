from pydantic import BaseModel, Field
from typing import List, Optional

class FosterState(BaseModel):
    # Resource Meters
    oxygen: int = 100
    fuel: int = 0
    
    # Hidden Roles (Server-side only)
    saboteur_id: Optional[str] = None
    
    # Game Phase
    cycle_count: int = 0
    phase: str = "day" # 'day' or 'night'
    
    # Log of recent events for the context window
    daily_logs: List[str] = Field(default_factory=list)

    def consume_oxygen(self, amount: int):
        self.oxygen = max(0, self.oxygen - amount)

    def add_fuel(self, amount: int):
        self.fuel = min(100, self.fuel + amount)
