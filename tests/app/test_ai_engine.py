import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.ai_engine import AIEngine

# Since conftest.py mocks the modules, we need to ensure the async methods 
# return values that the code expects (like .content and .response_metadata)

@pytest.mark.asyncio
async def test_ai_engine_initialization():
    """Verify the class initializes and loads config."""
    engine = AIEngine()
    assert engine.project_id == "test-project"  # From conftest env var
    assert engine.default_model_name == "gemini-2.5-flash"
    # Verify safety settings loaded (even if they are Mocks due to conftest)
    assert engine.safety_settings is not None

@pytest.mark.asyncio
async def test_generate_response_success():
    """Verify the happy path for generating a response."""
    engine = AIEngine()

    # We patch the class that AIEngine imports to control the instance it creates
    with patch("app.ai_engine.ChatVertexAI") as MockChatClass:
        # 1. Setup the Mock Model Instance
        mock_model_instance = MockChatClass.return_value
        
        # 2. Setup the "Result" object that ainvoke returns
        mock_result = MagicMock()
        mock_result.content = "This is a test response."
        mock_result.response_metadata = {
            "finish_reason": "STOP",
            "usage_metadata": {
                "prompt_token_count": 15,
                "candidates_token_count": 20,
                "total_tokens": 35
            }
        }
        
        # 3. Make ainvoke() an async function that returns our result
        # We need to mock both the direct model and the .bind() result
        mock_model_instance.ainvoke = AsyncMock(return_value=mock_result)
        mock_model_instance.bind.return_value.ainvoke = AsyncMock(return_value=mock_result)

        # 4. Run the method
        response = await engine.generate_response(
            system_prompt="You are a test bot.",
            conversation_id="game_123_thread_abc",
            user_input="Hello world"
        )

        # 5. Assertions
        assert response == "This is a test response."
        
        # Verify the model was called with correct messages
        # Note: We can check if ainvoke was called, but checking exact args 
        # is tricky with global variables. This is enough for a smoke test.
        assert mock_model_instance.ainvoke.called or mock_model_instance.bind.return_value.ainvoke.called

@pytest.mark.asyncio
async def test_generate_response_safety_block():
    """Verify behavior when AI returns empty content (Safety Filter)."""
    engine = AIEngine()

    with patch("app.ai_engine.ChatVertexAI") as MockChatClass:
        mock_model_instance = MockChatClass.return_value
        
        # Setup a blocked result (empty content)
        mock_result = MagicMock()
        mock_result.content = "" # Empty string triggers the safety block logic
        mock_result.response_metadata = {
            "finish_reason": "SAFETY",
            "safety_ratings": [{"category": "HARM_CATEGORY_HATE_SPEECH", "probability": "HIGH"}]
        }
        
        mock_model_instance.ainvoke = AsyncMock(return_value=mock_result)

        response = await engine.generate_response(
            system_prompt="Unsafe prompt",
            conversation_id="test_game_safety",
            user_input="Unsafe input"
        )

        # Should return empty string based on current logic
        assert response == ""

@pytest.mark.asyncio
async def test_generate_response_with_schema():
    """Verify that passing a schema triggers the bind() method."""
    engine = AIEngine()

    with patch("app.ai_engine.ChatVertexAI") as MockChatClass:
        mock_model_instance = MockChatClass.return_value
        mock_bound_model = mock_model_instance.bind.return_value
        
        # Setup successful return
        mock_result = MagicMock()
        mock_result.content = "{'key': 'value'}"
        mock_result.response_metadata = {"finish_reason": "STOP"}
        
        mock_bound_model.ainvoke = AsyncMock(return_value=mock_result)

        schema = {"type": "object", "properties": {"key": {"type": "string"}}}
        
        response = await engine.generate_response(
            system_prompt="JSON prompt",
            conversation_id="game_json",
            user_input="Give me JSON",
            response_schema=schema
        )

        assert response == "{'key': 'value'}"
        # Verify .bind() was called to attach the schema
        mock_model_instance.bind.assert_called_once()