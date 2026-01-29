import pytest
from unittest.mock import MagicMock, patch
from cartridges.foster_protocol.tools import execute_tool, TOOL_REGISTRY, MoveTool, GatherTool, WaitTool
from cartridges.foster_protocol.models import Caisson, Drone, Player, ChargingStation
from cartridges.foster_protocol.board import GameConfig

# --- FIXTURES ---

@pytest.fixture
def game_state():
    """Creates a fresh game state for each test."""
    state = Caisson()
    # Add a default drone
    drone = Drone(id="unit_01", location_id="stasis_bay", battery=50)
    state.drones["unit_01"] = drone
    # Add a target drone
    target = Drone(id="unit_02", location_id="stasis_bay", battery=50)
    state.drones["unit_02"] = target
    # Add a player
    state.players["p1"] = Player(id="p1", alive=True)
    return state

# --- TESTS ---

def test_tool_move_success(game_state):
    drone = game_state.drones["unit_01"]
    result = execute_tool("move", {"room_id": "engine_room"}, "unit_01", game_state)
    
    assert result.success is True
    assert drone.location_id == "engine_room"
    assert result.cost == MoveTool.COST

def test_tool_move_invalid_room(game_state):
    result = execute_tool("move", {"room_id": "void"}, "unit_01", game_state)
    assert result.success is False
    assert "not found" in result.message

def test_tool_gather_shuttle_bay(game_state):
    drone = game_state.drones["unit_01"]
    drone.location_id = "shuttle_bay"
    game_state.shuttle_bay_fuel = 20
    
    result = execute_tool("gather", {}, "unit_01", game_state)
    
    assert result.success is True
    assert "fuel_canister" in drone.inventory
    assert game_state.shuttle_bay_fuel == 10
    assert result.cost == GatherTool.COST

def test_tool_gather_torpedo_bay_explosion(game_state):
    drone = game_state.drones["unit_01"]
    drone.location_id = "torpedo_bay"
    game_state.torpedo_bay_fuel = 20
    
    # Mock random to trigger explosion (return < 0.05)
    with patch("random.randint", return_value=0):
        result = execute_tool("gather", {}, "unit_01", game_state)
        
    assert result.success is False
    assert "WARHEAD TRIGGERED" in result.message
    # Check if drone was EMP'd (battery 0)
    assert drone.battery == 0

def test_tool_deposit_success(game_state):
    drone = game_state.drones["unit_01"]
    drone.location_id = "engine_room"
    drone.inventory.append("fuel_canister")
    drone.inventory.append("fuel_canister")
    initial_fuel = game_state.fuel
    
    result = execute_tool("deposit", {}, "unit_01", game_state)
    
    assert result.success is True
    assert "fuel_canister" not in drone.inventory
    # 2 canisters * 10 fuel each
    assert game_state.fuel == initial_fuel + 20

def test_tool_deposit_fail_empty(game_state):
    drone = game_state.drones["unit_01"]
    drone.location_id = "engine_room"
    # No fuel in inventory
    
    result = execute_tool("deposit", {}, "unit_01", game_state)
    assert result.success is False

def test_tool_charge_success(game_state):
    drone = game_state.drones["unit_01"]
    drone.location_id = "charging_station"
    drone.battery = 10
    
    result = execute_tool("charge", {}, "unit_01", game_state)
    
    assert result.success is True
    assert drone.battery == 100

def test_tool_charge_disassembly(game_state):
    drone = game_state.drones["unit_01"]
    drone.location_id = "charging_station"
    game_state.station.pending_deactivation.append("unit_01")
    
    result = execute_tool("charge", {}, "unit_01", game_state)
    
    assert result.success is True
    assert "DESTROYED" in result.message
    assert drone.destroyed is True
    assert drone.battery == 0

def test_tool_tow_success(game_state):
    drone = game_state.drones["unit_01"]
    target = game_state.drones["unit_02"]
    
    # Both in same room
    drone.location_id = "shuttle_bay"
    target.location_id = "shuttle_bay"
    
    result = execute_tool("tow", {"target_id": "unit_02", "destination_id": "engine_room"}, "unit_01", game_state)
    
    assert result.success is True
    assert drone.location_id == "engine_room"
    assert target.location_id == "engine_room"

def test_tool_drain_success(game_state):
    drone = game_state.drones["unit_01"]
    target = game_state.drones["unit_02"]
    drone.battery = 50
    target.battery = 50
    
    result = execute_tool("drain", {"target_id": "unit_02"}, "unit_01", game_state)
    
    assert result.success is True
    assert target.battery == 30 # Drained 20
    
    assert drone.battery == 65 # Modified in execute
    assert result.cost == -15  # Returned cost
    
def test_tool_vent_success(game_state):
    initial_o2 = game_state.oxygen
    result = execute_tool("vent", {}, "unit_01", game_state)
    
    assert result.success is True
    assert game_state.oxygen == initial_o2 - GameConfig.OXYGEN_VENT_AMOUNT

def test_tool_siphon_success(game_state):
    drone = game_state.drones["unit_01"]
    drone.location_id = "engine_room"
    game_state.add_fuel(20)
    initial_fuel = game_state.fuel
    
    result = execute_tool("siphon", {}, "unit_01", game_state)
    
    assert result.success is True
    assert game_state.fuel == initial_fuel - 10
    assert "fuel_canister" in drone.inventory

def test_tool_search_found(game_state):
    drone = game_state.drones["unit_01"]
    drone.location_id = "maintenance"
    
    with patch("random.randint", return_value=0): # Force success
        result = execute_tool("search", {}, "unit_01", game_state)
        
    assert result.success is True
    assert "Found: Plasma Torch" in result.message
    assert "plasma_torch" in drone.inventory

def test_tool_incinerate_drone(game_state):
    drone = game_state.drones["unit_01"]
    target = game_state.drones["unit_02"]
    drone.inventory.append("plasma_torch")
    
    result = execute_tool("incinerate_drone", {"target_id": "unit_02"}, "unit_01", game_state)
    
    assert result.success is True
    assert target.status == "destroyed"
    assert "plasma_torch" not in drone.inventory

def test_tool_incinerate_pod(game_state):
    drone = game_state.drones["unit_01"]
    drone.location_id = "stasis_bay"
    drone.inventory.append("plasma_torch")
    
    result = execute_tool("incinerate_pod", {"player_id": "p1"}, "unit_01", game_state)
    
    assert result.success is True
    assert game_state.players["p1"].alive is False
    assert "plasma_torch" not in drone.inventory

def test_tool_detonate(game_state):
    drone = game_state.drones["unit_01"]
    drone.location_id = "torpedo_bay"
    
    result = execute_tool("detonate", {}, "unit_01", game_state)
    
    assert result.success is True
    assert drone.battery == 0 # EMP effect

def test_tool_wait(game_state):
    result = execute_tool("wait", {}, "unit_01", game_state)
    assert result.success is True
    assert result.cost == WaitTool.COST

def test_tool_invalid_command_cost(game_state):
    """
    Ensures that if a drone hallucinates a command, they are still
    penalized the standard 'Wait' cost for the wasted cycle.
    """
    drone = game_state.drones["unit_01"]
    initial_battery = drone.battery
    
    result = execute_tool("teleport", {}, "unit_01", game_state)
    
    assert result.success is False
    assert result.cost == WaitTool.COST
    
    # CRITICAL: Battery must actually decrease
    assert drone.battery == initial_battery - WaitTool.COST