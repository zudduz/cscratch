from typing import Dict, Any
from .models import CaissonState, BotState, PlayerState
from .board import SHIP_MAP

class FosterProtocol:
    def __init__(self):
        default_state = CaissonState()
        default_state.bots["unit_01"] = BotState(
            id="unit_01", 
            system_prompt="You are Unit-01. You are nervous.",
            goal_summary="Keep the Cryo Bay safe."
        )

        self.meta = {
            "name": "The Foster Protocol",
            "description": "A social deduction game aboard a dying starship.",
            "version": "1.0",
            **default_state.model_dump()
        }
        
        self.system_prompt = """
        ROLE: You are the Game Master for 'The Foster Protocol'.
        SETTING: A spaceship running on emergency power.
        """

    async def handle_input(self, generic_state: dict, user_input: str, context: dict, tools) -> Dict[str, Any]:
        """
        Handles a raw message from a user.
        Args:
            generic_state: The current GameState dict.
            user_input: The text content.
            context: Metadata about the message (channel_id, etc).
            tools: AI toolbox.
        """
        
        # 1. INFLATE
        game_data = CaissonState(**generic_state.get('metadata', {}))
        channel_id = context.get('channel_id')

        # --- LOGIC START ---
        
        # Example: Check if message is in the correct channel
        # For now, we just log it to the context
        print(f"DEBUG: Message received in channel {channel_id}")

        if "report" in user_input.lower():
            status = f"**CYCLE {game_data.cycle}**\n"
            status += f"O2: {game_data.oxygen}% | FUEL: {game_data.fuel}%\n"
            return {
                "response": status,
                "state_update": generic_state 
            }

        # AI Turn
        dynamic_prompt = f"{self.system_prompt}\nSTATUS: Oxygen {game_data.oxygen}%"

        ai_response = await tools.ai.generate_response(
            system_prompt=dynamic_prompt,
            conversation_id=generic_state.get('id'), 
            user_input=user_input
        )
        
        # --- LOGIC END ---

        # 2. DEFLATE
        generic_state['metadata'] = game_data.model_dump()
        
        return {
            "response": ai_response,
            "state_update": generic_state 
        }
