import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from app.game_engine import GameEngine
from app.models import GameState, GameInterface

# --- MOCKS ---

class MockCartridge:
    def __init__(self):
        self.meta = {"name": "Test Cartridge", "version": "0.1"}

    async def on_game_start(self, state):
        return {
            "metadata": {"state": "started"},
            "messages": [{"channel": "main", "content": "Welcome"}]
        }

    async def handle_input(self, state, user_input, ctx, tools):
        if user_input == "crash":
            raise ValueError("Boom")
        return {
            "metadata": {"last_input": user_input},
            "channel_ops": [{"op": "create", "key": "secret"}]
        }

# --- FIXTURES ---

@pytest.fixture
def mock_db():
    # MAGIC FIX: new_callable=AsyncMock
    # This forces all attributes of the mock (like create_game_record) 
    # to be AsyncMocks by default, so they can be awaited.
    with patch("app.persistence.db", new_callable=AsyncMock) as mock:
        yield mock

@pytest.fixture
def engine(mock_db):
    # We patch the AI engine to avoid API costs during tests
    with patch("app.game_engine.AIEngine", return_value=MagicMock()):
        eng = GameEngine()
        # Mock the cartridge loader to return our dummy cartridge
        eng._load_cartridge = AsyncMock(return_value=MockCartridge())
        return eng

# --- TESTS ---

@pytest.mark.asyncio
async def test_start_new_game_flow(engine, mock_db):
    # 1. Setup
    mock_db.get_game_by_id.return_value = None # No existing game
    
    # 2. Action
    game_id = await engine.start_new_game("test-story", "user_123", "HostUser")
    
    # 3. Verify
    assert game_id is not None
    # Verify DB created record
    mock_db.create_game_record.assert_called_once()
    # Verify Host joined
    mock_db.add_player_to_game.assert_called_once()
    args, _ = mock_db.add_player_to_game.call_args
    assert args[0] == game_id
    assert args[1].id == "user_123"

@pytest.mark.asyncio
async def test_launch_match(engine, mock_db):
    # 1. Setup Data
    game_id = "test_game_id"
    fake_game = GameState(
        id=game_id, 
        story_id="test-story", 
        host_id="user_123", 
        status="setup", 
        created_at="2024-01-01T00:00:00Z"
    )
    mock_db.get_game_by_id.return_value = fake_game

    # 2. Action
    result = await engine.launch_match(game_id)

    # 3. Verify
    assert result["metadata"]["state"] == "started"
    mock_db.set_game_active.assert_called_with(game_id)
    mock_db.update_game_metadata.assert_called_once()

@pytest.mark.asyncio
async def test_dispatch_input_success(engine, mock_db):
    # 1. Setup Data
    channel_id = "chan_999"
    game_id = "game_555"
    
    # Mock finding game by channel
    fake_interface = GameInterface(main_channel_id=channel_id)
    fake_game = GameState(
        id=game_id, story_id="test", host_id="u1", status="active", 
        created_at="2024-01-01", interface=fake_interface
    )
    
    # When using AsyncMock, setting return_value sets the result of the await
    mock_db.get_game_by_id.return_value = fake_game

    # 2. Action
    await engine.dispatch_input(channel_id, "u2", "Player2", "Hello World", "game_555")

    # 3. Verify
    # Should call update_game_metadata_fields with the result from MockCartridge
    mock_db.update_game_metadata_fields.assert_called()
    call_args = mock_db.update_game_metadata_fields.call_args
    assert call_args[0][0] == game_id
    
    # FIXED ASSERTION: The Engine unwraps 'metadata' before saving.
    assert call_args[0][1] == {"last_input": "Hello World"}

@pytest.mark.asyncio
async def test_dispatch_input_ignored_if_game_ended(engine, mock_db):
    channel_id = "chan_dead"
    fake_game = GameState(
        id="g_dead", story_id="test", host_id="u1", status="ended",
        created_at="2024-01-01"
    )
    mock_db.get_game_by_channel_id.return_value = fake_game

    await engine.dispatch_input(channel_id, "u1", "me", "ping", "g_dead")

    # Should NOT hit the DB update
    mock_db.update_game_metadata_fields.assert_not_called