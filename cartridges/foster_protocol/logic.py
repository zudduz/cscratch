from typing import Dict, Any
# Relative import of the model
from .models import FosterState

class FosterProtocol:
    def __init__(self):
        # We initialize the default state here so the Engine can save it on creation
        default_state = FosterState()
        
        self.meta = {
            "name": "The Foster Protocol",
            "description": "A social deduction game aboard a dying starship.",
            "version": "1.0",
            # The Engine saves this dict as the initial 'metadata'
            **default_state.model_dump()
        }
        
        self.system_prompt = """
        ROLE: You are the Game Master for 'The Foster Protocol'.
        SETTING: A spaceship running on emergency power.
        TONE: Tense, mechanical, suspicious.
        OBJECTIVE: The players (Fosters) must survive the night.
        """

    async def play_turn(self, generic_state: dict, user_input: str, tools) -> Dict[str, Any]:
        """
        The Core Loop.
        Args:
            generic_state: The dict representation of the GameState (from game.model_dump())
            user_input: The player's message.
            tools: The AI toolbox.
        """
        
        # 1. INFLATE: Convert generic metadata dict -> Typed FosterState Object
        # generic_state['metadata'] contains our specific fields (oxygen, fuel, etc)
        game_data = FosterState(**generic_state.get('metadata', {}))

        # --- GAME LOGIC START ---
        
        # Example: Simple state manipulation based on input
        # (In a real game, the AI would decide this via tool calls)
        if "wait" in user_input.lower():
            game_data.consume_oxygen(1)
            game_data.daily_logs.append(f"Crew waited. Oxygen dropped to {game_data.oxygen}%")

        # Inject dynamic state into the prompt
        dynamic_prompt = f"{self.system_prompt}\nSTATUS: Oxygen {game_data.oxygen}% | Fuel {game_data.fuel}%"

        # Call AI
        ai_response = await tools.ai.generate_response(
            system_prompt=dynamic_prompt,
            conversation_id=generic_state.get('id'), 
            user_input=user_input
        )
        
        # --- GAME LOGIC END ---

        # 2. DEFLATE: Save the modified object back to the generic state
        # We update the 'metadata' field in the returned dictionary
        generic_state['metadata'] = game_data.model_dump()
        
        return {
            "response": ai_response,
            "state_update": generic_state # The Engine saves this back to DB
        }
