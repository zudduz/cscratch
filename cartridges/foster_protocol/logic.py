from typing import Dict, Any
# Relative import
from .models import CaissonState, BotState, PlayerState
from .board import SHIP_MAP

class FosterProtocol:
    def __init__(self):
        # Default State initialization
        default_state = CaissonState()
        
        # Spawn a test bot
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
        
        # The Mainframe Prompt (The Narrator)
        self.system_prompt = """
        ROLE: You are the Game Master for 'The Foster Protocol'.
        SETTING: A spaceship running on emergency power.
        TONE: Tense, mechanical, suspicious.
        """

    async def play_turn(self, generic_state: dict, user_input: str, tools) -> Dict[str, Any]:
        """
        The Core Loop.
        """
        
        # 1. INFLATE: Dict -> CaissonState
        game_data = CaissonState(**generic_state.get('metadata', {}))

        # --- LOGIC START ---
        
        # Example: Check Status
        if "report" in user_input.lower():
            status = f"**CYCLE {game_data.cycle}**\n"
            status += f"O2: {game_data.oxygen}% | FUEL: {game_data.fuel}%\n"
            
            # List Bots
            for b_id, bot in game_data.bots.items():
                state_str = "ACTIVE"
                if bot.status == "destroyed": state_str = "DESTROYED"
                elif bot.battery <= 0: state_str = "UNCONSCIOUS"
                
                tow_str = f" (Towing: {bot.towing_id})" if bot.towing_id else ""
                status += f"- **{b_id}**: {state_str} | Bat: {bot.battery}% | AP: {bot.action_points}{tow_str}\n"

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

        # 2. DEFLATE: CaissonState -> Dict
        generic_state['metadata'] = game_data.model_dump()
        
        return {
            "response": ai_response,
            "state_update": generic_state 
        }
