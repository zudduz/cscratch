import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from cartridges.foster_protocol.logic import FosterProtocol
from cartridges.foster_protocol.models import Caisson, Player, Drone
from app.engine_context import EngineContext
from cartridges.foster_protocol.board import GameConfig, GameEndState

# --- FIXTURES ---

@pytest.fixture
def cartridge():
    with patch("cartridges.foster_protocol.ai_templates._get_base_prompt", return_value="MOCK PROMPT"):
        return FosterProtocol()

@pytest.fixture
def mock_ctx():
    ctx = MagicMock(spec=EngineContext)
    ctx.game_id = "test_game"
    ctx.send = AsyncMock()
    ctx.reply = AsyncMock()
    ctx.schedule = MagicMock()
    ctx.end = AsyncMock()
    ctx.trigger_data = {
        "channel_id": "main_chan",
        "user_id": "player_1",
        "interface": {"channels": {"aux-comm": "main_chan"}}
    }
    return ctx

@pytest.fixture
def mock_tools():
    tools = MagicMock()
    tools.ai.generate_response = AsyncMock(return_value="AI_RESPONSE")
    return tools

# --- TESTS ---

@pytest.mark.asyncio
async def test_game_initialization(cartridge):
    """
    Verifies that while players are always Loyal, the Drone role is assigned
    correctly based on the random index.
    """
    players = [{"id": "p1", "name": "Alice"}, {"id": "p2", "name": "Bob"}]
    state = {"players": players}
    
    # Mocks:
    # 1. randint(0, 1) -> 0 (p1 is the saboteur owner)
    # 2. randint(0, 999) -> 100 (Drone ID for p1)
    # 3. randint(0, 999) -> 101 (Drone ID for p2)
    with patch("random.randint", side_effect=[0, 100, 101]): 
        result = await cartridge.on_game_start(state)
        
    game_data = Caisson(**result["metadata"])
    assert len(game_data.players) == 2
    
    # 1. Player Assertion: Players are always loyal now (unaware of their drone's nature)
    assert game_data.players["p1"].role == "loyal"
    assert game_data.players["p2"].role == "loyal"
    
    # 2. Drone Assertion: The drone bonded to p1 (unit_100) should be the saboteur
    saboteur_drone = game_data.drones["unit_100"]
    assert saboteur_drone.foster_id == "p1"
    assert saboteur_drone.role == "saboteur"
    
    # 3. Drone Assertion: The other drone is loyal
    loyal_drone = game_data.drones["unit_101"]
    assert loyal_drone.role == "loyal"

@pytest.mark.asyncio
async def test_oxygen_depletion_math(cartridge, mock_ctx, mock_tools):
    game_data = Caisson(oxygen=100)
    for i in range(5):
        game_data.players[f"p{i}"] = Player(is_alive=True)
        
    physics_report = cartridge._calculate_physics(game_data)
        
    assert physics_report["oxygen_drop"] == 20

@pytest.mark.asyncio
async def test_lifeboat_dilemma(cartridge, mock_ctx, mock_tools):
    game_data = Caisson(oxygen=100)
    game_data.players["p1"] = Player(alive=True) 
    game_data.players["p2"] = Player(alive=False) 
    game_data.players["p3"] = Player(alive=False) 
    game_data.players["p4"] = Player(alive=False) 
    game_data.players["p5"] = Player(alive=False) 
    
    physics_report = cartridge._calculate_physics(game_data)
        
    assert physics_report["oxygen_drop"] == 4 

@pytest.mark.asyncio
async def test_no_active_drones(cartridge, mock_ctx, mock_tools):
    game_data = Caisson(oxygen=100, fuel=40)
    game_data.players["p1"] = Player(alive=False) 
    game_data.players["p2"] = Player(alive=False) 
    game_data.drones["unit_303"] = Drone(id="unit_303", destroyed=True)
    game_data.drones["unit_313"] = Drone(id="unit_313", battery=0)
    
    physics_report = {
            "oxygen_drop": 20,
            "req_today": 60,
            "req_tomorrow": 70,
            "cycle_report_idx": 1
        }
    arbitration = cartridge._evaluate_arbitration(game_data, physics_report)
        
    assert arbitration == GameEndState.NO_ACTIVE_DRONES

@pytest.mark.asyncio
async def test_torpedo_explosion(cartridge, mock_ctx, mock_tools):
    game_data = Caisson()
    drone = MagicMock()
    drone.id = "unit_01"
    drone.location_id = "torpedo_bay"
    drone.battery = 100
    drone.inventory = []
    game_data.drones["unit_01"] = drone
    
    mock_tools.ai.generate_response.return_value = '''{"thought_chain": "Carefully gather fuel", "tool": "gather"}'''
    
    with patch("random.randint", return_value=0): 
        res = await cartridge.run_single_drone_turn(drone, game_data, 1, mock_tools, "game_id")
        
    assert res["result"].success is False
    assert "WARHEAD TRIGGERED" in res["result"].message
    # Battery should be 0 because EMP sets it to 0, and cost clamping keeps it there.
    assert drone.battery == 0

@pytest.mark.asyncio
async def test_gather_success(cartridge):
    initial_shuttle_fuel = GameConfig.CAPACITY_SHUTTLE_BAY
    gather_amount = 10 
    expected_remaining = initial_shuttle_fuel - gather_amount

    game_data = Caisson()
    drone = MagicMock()
    drone.id = "unit_01"
    drone.location_id = "shuttle_bay"
    drone.battery = 100
    drone.inventory = []
    game_data.drones["unit_01"] = drone
    
    mock_tools = MagicMock()
    mock_tools.ai.generate_response = AsyncMock(return_value='''{"tool": "gather"}''')
    
    res = await cartridge.run_single_drone_turn(drone, game_data, 1, mock_tools, "game_id")
    
    assert res["result"].success is True
    assert "fuel_canister" in drone.inventory
    assert game_data.shuttle_bay_fuel == expected_remaining