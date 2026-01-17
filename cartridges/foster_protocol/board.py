# STATIC CONFIGURATION - THE RULE BOOK

class GameConfig:
    # --- RESOURCES ---
    INITIAL_OXYGEN = 100
    OXYGEN_BASE_LOSS = 20  # Base daily drop (scaled by crew size)
    
    INITIAL_FUEL = 0
    MAX_FUEL = 100
    FUEL_PER_CANISTER = 10
    
    # --- ROOM CAPACITIES (Total Fuel available to gather) ---
    CAPACITY_SHUTTLE_BAY = 50  # 5 Canisters
    CAPACITY_TORPEDO_BAY = 80  # 8 Canisters
    
    # --- ORBITAL MECHANICS ---
    FUEL_REQ_BASE = 50
    FUEL_REQ_GROWTH = 1.2  # Exponential difficulty curve
    MAX_POSSIBLE_FUEL_REQ = 100 # If req exceeds this, game is lost mathematically

class ActionCosts:
    # Legacy costs (reference only, actual costs in tools.py)
    # Ideally, tools.py should import these too, but we'll start here.
    MOVE = 12
    GATHER = 15
    DEPOSIT = 15
    CHARGE = 0    
    TOW = 20      
    DRAIN = -15   
    SABOTAGE = 20 
    KILL = 50     

class RoomDef:
    def __init__(self, name: str, description: str, can_nanny: bool = False):
        self.name = name
        self.description = description
        self.can_nanny = can_nanny

# The Map Definitions
SHIP_MAP = {
    "cryo_bay": RoomDef(
        name="Cryo Bay", 
        description="Rows of frosted pods. The air is breathable here.",
        can_nanny=True
    ),
    "engine_room": RoomDef(
        name="Engine Room", 
        description="The roaring heart of the ship. Intense radiation. Deposit Fuel here.",
    ),
    "shuttle_bay": RoomDef(
        name="Shuttle Bay", 
        description="Cargo crates and a docked shuttle. Good source of fuel.",
    ),
    "torpedo_bay": RoomDef(
        name="Torpedo Bay", 
        description="Volatile munitions storage. Cold and dark. High Fuel Yield.",
    ),
    "maintenance": RoomDef(
        name="Maintenance Station",
        description="Diagnostic computers. Search here for tools (Plasma Torch).",
    ),
    "charging_station": RoomDef(
        name="Charging Station",
        description="High voltage couplings. The only place to restore Battery.",
    )
}
