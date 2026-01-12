# STATIC CONFIGURATION - DO NOT STORE IN DB

class ActionCosts:
    MOVE = 1
    SIPHON = 3
    DEPOSIT = 1
    TOW = 5
    SABOTAGE_O2 = 2

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
        description="The roaring heart of the ship. Intense radiation.",
    ),
    "shuttle_bay": RoomDef(
        name="Shuttle Bay", 
        description="Cargo crates and a docked shuttle. Good source of fuel.",
    ),
    "torpedo_bay": RoomDef(
        name="Torpedo Bay", 
        description="Volatile munitions storage. Cold and dark.",
    ),
    "maintenance": RoomDef(
        name="Maintenance Station",
        description="Diagnostic computers and charging cradles.",
    )
}
