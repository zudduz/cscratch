import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from cartridges.foster_protocol.logic import FosterProtocol
from cartridges.foster_protocol.models import CaissonState, PlayerState
from app.engine_context import EngineContext

# --- FIXTURES ---

@pytest.fixture
def cartridge():
    with patch.object(FosterProtocol, "_load_base_prompt", return_value="MOCK PROMPT"):
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
    players = [{"id": "p1", "name": "Alice"}, {"id": "p2", "name": "Bob"}]
    state = {"players": players}
    with patch("random.randint", side_effect=[0, 100, 101]): 
        result = await cartridge.on_game_start(state)
    game_data = CaissonState(**result["metadata"])
    assert len(game_data.players) == 2
    assert game_data.players["p1"].role == "saboteur"

@pytest.mark.asyncio
async def test_oxygen_depletion_math(cartridge, mock_ctx, mock_tools):
    game_data = CaissonState(initial_crew_size=5, oxygen=100)
    for i in range(5):
        game_data.players[f"p{i}"] = PlayerState(is_alive=True)
    with patch("asyncio.sleep", AsyncMock()), \
         patch.object(cartridge, "run_single_drone_turn", AsyncMock(return_value={
             "drone": MagicMock(), "action": {}, "result": MagicMock(message="ok", visibility="private"), "thought": "x"
         })):
        result_state = await cartridge.execute_day_simulation(game_data, mock_ctx, mock_tools)
    new_state = CaissonState(**result_state)
    # Base Loss is 20 per day (regardless of shift length)
    assert new_state.oxygen == 80

@pytest.mark.asyncio
async def test_lifeboat_dilemma(cartridge, mock_ctx, mock_tools):
    game_data = CaissonState(initial_crew_size=5, oxygen=100)
    game_data.players["p1"] = PlayerState(is_alive=True) 
    with patch("asyncio.sleep", AsyncMock()), \
         patch.object(cartridge, "run_single_drone_turn", AsyncMock(return_value={
             "drone": MagicMock(), "action": {}, "result": MagicMock(message="ok", visibility="private"), "thought": "x"
         })):
        result_state = await cartridge.execute_day_simulation(game_data, mock_ctx, mock_tools)
    new_state = CaissonState(**result_state)
    # 20 * (1/5) = 4 loss
    assert new_state.oxygen == 96 

@pytest.mark.asyncio
async def test_torpedo_explosion(cartridge, mock_ctx, mock_tools):
    game_data = CaissonState()
    drone = MagicMock()
    drone.id = "unit_01"
    drone.location_id = "torpedo_bay"
    drone.battery = 100
    drone.inventory = []
    game_data.drones["unit_01"] = drone
    mock_tools.ai.generate_response.return_value = '{"tool": "gather", "args": {}}'
    with patch("random.random", return_value=0.01): 
        res = await cartridge.run_single_drone_turn(drone, game_data, 1, mock_tools, "game_id")
    assert res["result"].success is False
    assert "CRITICAL FAILURE" in res["result"].message
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
    
    res = await cartridge.run_single_drone_turn(drone, game_data, 1, mock_tools, "game_id")
    
    assert res["result"].success is True
    assert "fuel_canister" in drone.inventory
    
    # REBALANCE FIX:
    # Initial Capacity: 16 (from board.py)
    # Gather Amount: 10
    # Remaining: 6
    assert game_data.shuttle_bay_fuel == 6