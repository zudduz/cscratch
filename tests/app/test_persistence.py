import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.persistence import PersistenceLayer
from app.models import AILogEntry

@pytest.mark.asyncio
async def test_log_ai_interaction():
    """Verify the logging method calls the correct Firestore chain."""
    
    # 1. Create the final destination mock (the logs collection)
    mock_logs_col = MagicMock()
    # The .add method must be async
    mock_logs_col.add = AsyncMock()

    # 2. Create the document mock that returns the logs collection
    mock_game_doc = MagicMock()
    mock_game_doc.collection.return_value = mock_logs_col

    # 3. Create the games collection mock that returns the game doc
    mock_games_col = MagicMock()
    mock_games_col.document.return_value = mock_game_doc

    # 4. Patch the Firestore Client to return our chain
    mock_client = MagicMock()
    mock_client.collection.return_value = mock_games_col
    
    with patch("app.persistence.firestore.AsyncClient", return_value=mock_client):
        persistence = PersistenceLayer()
        # Force the internal client to be our mock (just in case init creates a new one)
        persistence.db = mock_client 
        persistence.games_collection = mock_games_col

        entry = AILogEntry(
            game_id="test_game",
            model="gemini",
            system_prompt="sys",
            user_input="user",
            raw_response="resp",
            usage={}
        )
        
        await persistence.log_ai_interaction(entry)
        
        # Verify
        mock_games_col.document.assert_called_with("test_game")
        mock_game_doc.collection.assert_called_with("logs")
        mock_logs_col.add.assert_called_once()