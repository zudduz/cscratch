from enum import Enum

class GameConfig(int, Enum):
    HOURS_PER_SHIFT = 8
    INITIAL_OXYGEN = 100
    OXYGEN_BASE_LOSS = 20
    OXYGEN_VENT_AMOUNT = 5
    
    INITIAL_FUEL = 0
    MAX_FUEL = 100
    FUEL_PER_CANISTER = 10
    
    CAPACITY_SHUTTLE_BAY = 60
    CAPACITY_TORPEDO_BAY = 120
    
    TORPEDO_ACCIDENT_PERCENT = 5
    PLASMA_TORCH_DISCOVERY_PERCENT = 20
    
    FUEL_REQ_BASE = 49
    FUEL_REQ_GROWTH_PERCENT = 115
    MAX_POSSIBLE_FUEL_REQ = 100 

    MAX_TARGET_DRAIN_AMOUNT = 20
    MAX_DRAIN_BENEFIT = 15   

class Room(str, Enum):
    STASIS_BAY = "stasis_bay"
    ENGINE_ROOM = "engine_room"
    SHUTTLE_BAY = "shuttle_bay"
    TORPEDO_BAY = "torpedo_bay"
    MAINTENANCE = "maintenance"
    CHARGING_STATION = "charging_station"
