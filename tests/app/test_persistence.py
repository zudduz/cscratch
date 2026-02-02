import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.persistence import PersistenceLayer
from app.models import AILogEntry

@pytest.mark.asyncio
async def test_log_ai_interaction():
    """Verify the logging method calls the correct Firestore chain."""
    
    # Mock Firestore Client
    mock_firestore = MagicMock()
    
    # Patch the AsyncClient to return our mock
    with patch("google.cloud.firestore.AsyncClient", return_value=mock_firestore):
        persistence = PersistenceLayer()
        
        # Setup the chain: collection -> document -> collection -> add
        mock_game_ref = MagicMock()
        mock_logs_col = MagicMock()
        mock_logs_col.add = AsyncMock() # The actual async call
        
        mock_firestore.collection.return_value.document.return_value = mock_game_ref
        mock_game_ref.collection.return_value = mock_logs_col
        
        # Create dummy entry
        entry = AILogEntry(
            game_id="test_game",
            model="gemini",
            system_prompt="sys",
            user_input="user",
            raw_response="resp"
        )
        
        await persistence.log_ai_interaction(entry)
        
        # Verify the chain was called with correct ID and Collection Name
        mock_firestore.collection.assert_called_with("games")
        mock_firestore.collection.return_value.document.assert_called_with("test_game")
        mock_game_ref.collection.assert_called_with("logs")
        mock_logs_col.add.assert_called_once()