# STATIC CONFIGURATION - DO NOT STORE IN DB

class ActionCosts:
    # Legacy costs (reference only, actual costs in tools.py)
    MOVE = 12
    SIPHON = 20
    DEPOSIT = 15
    TOW = 20
    SABOTAGE_O2 = 20

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
