import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from cartridges.foster_protocol.logic import FosterProtocol
from cartridges.foster_protocol.models import Caisson, Player, Drone
from app.engine_context import EngineContext

# --- FIXTURES ---

@pytest.fixture
def cartridge():
    return FosterProtocol()

@pytest.fixture
def mock_ctx():
    ctx = MagicMock(spec=EngineContext)
    ctx.game_id = "test_game"
    ctx.reply = AsyncMock()
    ctx.send = AsyncMock()
    ctx.schedule = MagicMock()
    # Default trigger data (will be overridden in tests)
    ctx.trigger_data = {
        "channel_id": "aux_comm_id",
        "user_id": "u1",
        "interface": {
            "channels": {
                "aux-comm": "aux_comm_id", 
                "nanny_u1": "nanny_u1_id",
                "nanny_u2": "nanny_u2_id"
            }
        }
    }
    return ctx

@pytest.fixture
def mock_tools():
    tools = MagicMock()
    tools.ai.generate_response = AsyncMock(return_value="AI_RESPONSE")
    return tools

@pytest.fixture
def base_state():
    """Creates a standard 2-player, 2-drone setup."""
    state = Caisson()
    
    # Players
    state.players["u1"] = Player(id="u1", name="Alice", alive=True)
    state.players["u2"] = Player(id="u2", name="Bob", alive=True)
    
    # Drones
    state.drones["d1"] = Drone(id="d1", foster_id="u1", battery=100)
    state.drones["d2"] = Drone(id="d2", foster_id="u2", battery=100)
    
    return state.model_dump()

# --- TESTS ---

@pytest.mark.asyncio
async def test_input_blocked_during_day_phase(cartridge, mock_ctx, mock_tools, base_state):
    """Ensure no commands work while the simulation is running."""
    # Modify state to be in 'day' phase (Fix: Access phase directly on the state dict)
    base_state['phase'] = 'day'
    
    await cartridge.handle_input({"metadata": base_state}, "!destroy d1", mock_ctx, mock_tools)
    
    # Should reply with snarky message, not execute command
    mock_ctx.reply.assert_called_with("Day Cycle in progress. You are sleeping now. Pretend to snore or something.")
    assert "d1" not in base_state['station']['pending_deactivation'] # Should not have triggered

@pytest.mark.asyncio
async def test_destroy_permission_owner(cartridge, mock_ctx, mock_tools, base_state):
    """User u1 should be able to destroy d1 (their own drone)."""
    mock_ctx.trigger_data["user_id"] = "u1"
    
    result = await cartridge.handle_input({"metadata": base_state}, "!destroy d1", mock_ctx, mock_tools)
    
    # Check return patch
    assert "station" in result
    assert "d1" in result["station"]["pending_deactivation"]
    assert "DESTRUCTION AUTHORIZED" in mock_ctx.reply.call_args[0][0]

@pytest.mark.asyncio
async def test_destroy_permission_denied_non_owner(cartridge, mock_ctx, mock_tools, base_state):
    """User u1 should NOT be able to destroy d2 (Bob's drone)."""
    mock_ctx.trigger_data["user_id"] = "u1"
    
    result = await cartridge.handle_input({"metadata": base_state}, "!destroy d2", mock_ctx, mock_tools)
    
    assert result is None
    assert "DENIED" in mock_ctx.reply.call_args[0][0]

@pytest.mark.asyncio
async def test_destroy_permission_allowed_orphan(cartridge, mock_ctx, mock_tools, base_state):
    """User u1 SHOULD be able to destroy d2 IF Bob is dead."""
    # Kill Bob
    state_obj = Caisson(**base_state)
    state_obj.players["u2"].alive = False
    serialized_state = state_obj.model_dump()
    
    mock_ctx.trigger_data["user_id"] = "u1"
    
    result = await cartridge.handle_input({"metadata": serialized_state}, "!destroy d2", mock_ctx, mock_tools)
    
    assert "station" in result
    assert "d2" in result["station"]["pending_deactivation"]

@pytest.mark.asyncio
async def test_sleep_consensus_partial(cartridge, mock_ctx, mock_tools, base_state):
    """1 out of 2 players sleeping should NOT trigger day."""
    # u1 is sending the command in their nanny channel
    mock_ctx.trigger_data["user_id"] = "u1"
    mock_ctx.trigger_data["channel_id"] = "nanny_u1_id"
    
    result = await cartridge.handle_input({"metadata": base_state}, "!sleep", mock_ctx, mock_tools)
    
    # Should patch u1's sleep state
    assert "players.u1.requested_sleep" in result
    assert result["players.u1.requested_sleep"] is True
    
    # Should confirm logging
    assert "Sleep request logged" in mock_ctx.reply.call_args[0][0]
    # Should NOT have scheduled simulation
    mock_ctx.schedule.assert_not_called()

@pytest.mark.asyncio
async def test_sleep_consensus_complete(cartridge, mock_ctx, mock_tools, base_state):
    """2 out of 2 players sleeping SHOULD trigger day."""
    # Set u2 to already sleeping
    state_obj = Caisson(**base_state)
    state_obj.players["u2"].requested_sleep = True
    serialized_state = state_obj.model_dump()
    
    mock_ctx.trigger_data["user_id"] = "u1"
    mock_ctx.trigger_data["channel_id"] = "nanny_u1_id"
    
    with patch.object(cartridge, "execute_day_simulation", new_callable=MagicMock) as mock_sim:
        result = await cartridge.handle_input({"metadata": serialized_state}, "!sleep", mock_ctx, mock_tools)
    
        assert "Sleep request logged" in mock_ctx.reply.call_args[0][0]
        
        # Should return full metadata update (phase change)
        assert result["metadata"]["phase"] == "day"
        
        # Should schedule the simulation (which is now the mock result)
        mock_ctx.schedule.assert_called_once_with(mock_sim.return_value)

@pytest.mark.asyncio
async def test_mainframe_chat_routing(cartridge, mock_ctx, mock_tools, base_state):
    """Input without ! in aux-comm should go to Mainframe AI."""
    mock_ctx.trigger_data["channel_id"] = "aux_comm_id"
    
    await cartridge.handle_input({"metadata": base_state}, "Open the pod bay doors", mock_ctx, mock_tools)
    
    # Check conversation ID uses mainframe suffix
    call_args = mock_tools.ai.generate_response.call_args
    assert "mainframe" in call_args[0][1] # conversation_id
    assert "VENDETTA OPERATING SYSTEM" in call_args[0][0] # system_prompt snippet

@pytest.mark.asyncio
async def test_nanny_chat_routing(cartridge, mock_ctx, mock_tools, base_state):
    """Input without ! in nanny channel should go to Drone AI."""
    mock_ctx.trigger_data["user_id"] = "u1"
    mock_ctx.trigger_data["channel_id"] = "nanny_u1_id"
    
    await cartridge.handle_input({"metadata": base_state}, "I love you drone", mock_ctx, mock_tools)
    
    # Check conversation ID uses drone ID suffix
    call_args = mock_tools.ai.generate_response.call_args
    assert "d1" in call_args[0][1] # conversation_id should contain drone id
    
    # Check log update returned
    mock_ctx.reply.assert_called_with("AI_RESPONSE")