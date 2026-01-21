# STATIC CONFIGURATION - THE RULE BOOK

class GameConfig:
    # --- TIME ---
    HOURS_PER_SHIFT = 8  # Keeping the 8-hour shift

    # --- RESOURCES ---
    INITIAL_OXYGEN = 100
    OXYGEN_BASE_LOSS = 20
    OXYGEN_VENT_AMOUNT = 10
    
    INITIAL_FUEL = 0
    MAX_FUEL = 100
    FUEL_PER_CANISTER = 10
    
    # --- ROOM CAPACITIES ---
    CAPACITY_SHUTTLE_BAY = 50  # REVERTED: Back to 5 canisters (Safe Zone)
    CAPACITY_TORPEDO_BAY = 80
    
    # --- RISKS ---
    TORPEDO_ACCIDENT_CHANCE = 0.05  # 5% chance per gather attempt
    
    # --- ORBITAL MECHANICS ---
    FUEL_REQ_BASE = 50
    FUEL_REQ_GROWTH = 1.2
    MAX_POSSIBLE_FUEL_REQ = 100 

class ActionCosts:
    MOVE = 12
    GATHER = 15
    DEPOSIT = 15
    CHARGE = 0    
    TOW = 20      
    DRAIN = -15   
    SABOTAGE = 20 
    KILL = 50
    DETONATE = 10 # Cost to trigger the warhead manually

class RoomDef:
    def __init__(self, name: str, description: str, can_nanny: bool = False):
        self.name = name
        self.description = description
        self.can_nanny = can_nanny

SHIP_MAP = {
    "stasis_bay": RoomDef(
        name="Stasis Bay", 
        description="Rows of sealed stasis pods. The air is breathable here.",
        can_nanny=True
    ),
    "engine_room": RoomDef(
        name="Engine Room", 
        description="The roaring heart of the ship. Intense radiation. Deposit Fuel here.",
    ),
    "shuttle_bay": RoomDef(
        name="Shuttle Bay", 
        description="Cargo crates and a docked shuttle. Safe fuel source.",
    ),
    "torpedo_bay": RoomDef(
        name="Torpedo Bay", 
        description="Volatile munitions. HIGH YIELD. HIGH RISK. 5% Explosion Chance per Gather.",
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
