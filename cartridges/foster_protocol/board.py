# STATIC CONFIGURATION - THE RULE BOOK

class GameConfig:
    HOURS_PER_SHIFT = 8
    INITIAL_OXYGEN = 100
    OXYGEN_BASE_LOSS = 20
    OXYGEN_VENT_AMOUNT = 5
    
    INITIAL_FUEL = 0
    MAX_FUEL = 100
    FUEL_PER_CANISTER = 10
    
    CAPACITY_SHUTTLE_BAY = 60
    CAPACITY_TORPEDO_BAY = 120
    
    TORPEDO_ACCIDENT_CHANCE = 0.05
    PLASMA_TORCH_DISCOVERY_CHANCE = 0.2
    
    FUEL_REQ_BASE = 49
    FUEL_REQ_GROWTH = 1.15
    MAX_POSSIBLE_FUEL_REQ = 100 

class ActionCosts:
    WAIT = 6      
    MOVE = 8      
    GATHER = 10   
    DEPOSIT = 10  
    CHARGE = -100    
    TOW = 20      
    DRAIN = -15   
    SABOTAGE = 12 
    KILL = 30     
    DETONATE = 10

# Simplified Map: Code only cares about valid IDs
SHIP_MAP = {
    "stasis_bay": {"can_nanny": True},
    "engine_room": {},
    "shuttle_bay": {},
    "torpedo_bay": {},
    "maintenance": {},
    "charging_station": {}
}
