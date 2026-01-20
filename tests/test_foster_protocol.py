import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from cartridges.foster_protocol.logic import FosterProtocol
from cartridges.foster_protocol.models import CaissonState, PlayerState
from app.engine_context import EngineContext

# --- FIXTURES ---

@pytest.fixture
def cartridge():
    # Patch the prompt loader so we don't need the file on disk during tests
    with patch.object(FosterProtocol, "_load_base_prompt", return_value="MOCK PROMPT"):
        return FosterProtocol()

@pytest.fixture
def mock_ctx():
    # A dummy engine context
    ctx = MagicMock(spec=EngineContext)
    ctx.game_id = "test_game"
    ctx.send = AsyncMock()
    ctx.reply = AsyncMock()
    ctx.schedule = MagicMock()
    ctx.end = AsyncMock()
    # Basic trigger data for input handling
    ctx.trigger_data = {
        "channel_id": "main_chan",
        "user_id": "player_1",
        "interface": {"channels": {"aux-comm": "main_chan"}}
    }
    return ctx

@pytest.fixture
def mock_tools():
    # Mock the AI Engine so we don't hit Vertex
    tools = MagicMock()
    tools.ai.generate_response = AsyncMock(return_value="AI_RESPONSE")
    return tools

# --- TESTS ---

@pytest.mark.asyncio
async def test_game_initialization(cartridge):
    # Setup players
    players = [
        {"id": "p1", "name": "Alice"},
        {"id": "p2", "name": "Bob"}
    ]
    state = {"players": players}

    # Force RNG to pick index 0 (Alice) as Saboteur
    with patch("random.randint", side_effect=[0, 100, 101]): 
        result = await cartridge.on_game_start(state)

    game_data = CaissonState(**result["metadata"])
    
    # Assertions
    assert len(game_data.players) == 2
    assert game_data.players["p1"].role == "saboteur"
    assert game_data.players["p2"].role == "loyal"
    assert len(game_data.drones) == 2
    # Ensure drones were created with the right foster parents
    drones = list(game_data.drones.values())
    assert drones[0].foster_id == "p1"
    assert drones[0].role == "saboteur" # Saboteur player gets saboteur drone

@pytest.mark.asyncio
async def test_oxygen_depletion_math(cartridge, mock_ctx, mock_tools):
    # Setup: 5 Players, Oxygen 100
    game_data = CaissonState(initial_crew_size=5, oxygen=100)
    # Populate with 5 ALIVE players using PlayerState objects
    for i in range(5):
        game_data.players[f"p{i}"] = PlayerState(is_alive=True)
    
    # Run the day loop (mocking the time.sleep and drone turns)
    with patch("asyncio.sleep", AsyncMock()),          patch.object(cartridge, "run_single_drone_turn", AsyncMock(return_value={
             "drone": MagicMock(), "action": {}, "result": MagicMock(message="ok", visibility="private"), "thought": "x"
         })):
        
        result_state = await cartridge.execute_day_simulation(game_data, mock_ctx, mock_tools)
        
    # Math: Base Loss 20 * (5/5) = 20 loss
    new_state = CaissonState(**result_state)
    assert new_state.oxygen == 80
    assert new_state.cycle == 2

@pytest.mark.asyncio
async def test_lifeboat_dilemma(cartridge, mock_ctx, mock_tools):
    # Setup: 5 Initial Crew, but only 1 Alive (4 Dead)
    game_data = CaissonState(initial_crew_size=5, oxygen=100)
    game_data.players["p1"] = PlayerState(is_alive=True) 
    # Others missing/dead
    
    with patch("asyncio.sleep", AsyncMock()),          patch.object(cartridge, "run_single_drone_turn", AsyncMock(return_value={
             "drone": MagicMock(), "action": {}, "result": MagicMock(message="ok", visibility="private"), "thought": "x"
         })):
        
        result_state = await cartridge.execute_day_simulation(game_data, mock_ctx, mock_tools)

    # Math: Base Loss 20 * (1/5) = 4 loss
    new_state = CaissonState(**result_state)
    assert new_state.oxygen == 96 # Much slower drain!

@pytest.mark.asyncio
async def test_torpedo_explosion(cartridge, mock_ctx, mock_tools):
    # Setup: Drone in Torpedo Bay
    game_data = CaissonState()
    drone = MagicMock()
    drone.id = "unit_01"
    drone.location_id = "torpedo_bay"
    drone.battery = 100
    drone.inventory = []
    
    game_data.drones["unit_01"] = drone
    
    # 1. Force the AI to choose "gather"
    # 2. Force the random check to fail ( < 0.05 )
    mock_tools.ai.generate_response.return_value = '{"tool": "gather", "args": {}}'
    
    with patch("random.random", return_value=0.01): # Boom
        # Run just the turn helper directly
        res = await cartridge.run_single_drone_turn(drone, game_data, 1, mock_tools, "game_id")
        
    assert res["result"].success is False
    assert "CRITICAL FAILURE" in res["result"].message
    # Drone should be dead (battery 0)
    assert drone.battery == 0

@pytest.mark.asyncio
async def test_gather_success(cartridge, mock_ctx, mock_tools):
    # Setup: Drone in Shuttle Bay (Safe)
    game_data = CaissonState()
    drone = MagicMock()
    drone.id = "unit_01"
    drone.location_id = "shuttle_bay"
    drone.battery = 100
    drone.inventory = []
    
    game_data.drones["unit_01"] = drone
    
    mock_tools.ai.generate_response.return_value = '{"tool": "gather", "args": {}}'
    
    # Run turn
    res = await cartridge.run_single_drone_turn(drone, game_data, 1, mock_tools, "game_id")
    
    assert res["result"].success is True
    assert "fuel_canister" in drone.inventory
    assert game_data.shuttle_bay_fuel == 40 # Started at 50, -10
