from typing import Dict, Any
import random

# Relative imports
from .models import FosterState, BotState
from .board import SHIP_MAP, ActionCosts

class FosterProtocol:
    def __init__(self):
        # Initialize Default State
        # In a real game, we might randomize this or set it up based on player count
        default_state = FosterState()
        
        # Example: Pre-spawn a bot for testing
        default_state.bots["unit_01"] = BotState(id="unit_01", role="loyal")

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
        """
        
        # 1. INFLATE: Convert generic metadata dict -> Typed FosterState Object
        game_data = FosterState(**generic_state.get('metadata', {}))

        # --- GAME LOGIC START ---
        
        # Example: Simple debug command to test the map
        if "scan" in user_input.lower():
            status = f"LOCATION: {SHIP_MAP['cryo_bay'].description}\n"
            status += f"OXYGEN: {game_data.oxygen}% | FUEL: {game_data.fuel}%"
            
            return {
                "response": status,
                "state_update": generic_state 
            }

        # Inject dynamic state into the prompt
        # We give the AI the current context of the ship
        dynamic_prompt = f"{self.system_prompt}\nSTATUS: Oxygen {game_data.oxygen}% | Fuel {game_data.fuel}%"

        # Call AI
        ai_response = await tools.ai.generate_response(
            system_prompt=dynamic_prompt,
            conversation_id=generic_state.get('id'), 
            user_input=user_input
        )
        
        # --- GAME LOGIC END ---

        # 2. DEFLATE: Save the modified object back to the generic state
        generic_state['metadata'] = game_data.model_dump()
        
        return {
            "response": ai_response,
            "state_update": generic_state 
        }
