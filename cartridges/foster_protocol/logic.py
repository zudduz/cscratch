from typing import Dict, Any, List
import random
from .models import CaissonState, BotState, PlayerState
from .board import SHIP_MAP

class FosterProtocol:
    def __init__(self):
        default_state = CaissonState()
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

    async def on_game_start(self, generic_state: dict):
        """
        Called once when the game transitions from Lobby -> Active.
        Responsibility: Generate Bots, Assign Roles.
        """
        game_data = CaissonState(**generic_state.get('metadata', {}))
        
        # 1. Get Players from the Generic State (The Discord Users)
        # generic_state['players'] is a list of dicts: {'id': '123', 'name': 'Skippy'}
        discord_players = generic_state.get('players', [])
        
        if not discord_players:
            return generic_state # Should not happen

        # 2. Assign Roles (1 Saboteur)
        saboteur_index = random.randint(0, len(discord_players) - 1)
        
        # 3. Generate Entities
        for i, p_data in enumerate(discord_players):
            u_id = p_data['id']
            u_name = p_data['name']
            
            # Determine Role
            is_saboteur = (i == saboteur_index)
            role = "saboteur" if is_saboteur else "loyal"
            
            # Create PlayerState
            game_data.players[u_id] = PlayerState(role=role)
            
            # Create BotState
            bot_id = f"unit_{str(u_id)[-3:]}" # Unit-734 (Last 3 digits of User ID)
            
            prompt = f"You are {bot_id}. You serve {u_name}."
            if is_saboteur:
                prompt += " You are the Saboteur. Fake your loyalty."
            
            game_data.bots[bot_id] = BotState(
                id=bot_id,
                foster_id=u_id,
                role=role,
                system_prompt=prompt,
                goal_summary="Survive."
            )
            
            # Log it
            game_data.daily_logs.append(f"SYSTEM: {bot_id} came online. Bonded to Foster {u_name}.")

        # 4. Save
        generic_state['metadata'] = game_data.model_dump()
        return generic_state

    async def handle_input(self, generic_state: dict, user_input: str, context: dict, tools) -> Dict[str, Any]:
        game_data = CaissonState(**generic_state.get('metadata', {}))
        
        if "report" in user_input.lower():
            status = f"**CYCLE {game_data.cycle}**\n"
            for b_id, bot in game_data.bots.items():
                owner = bot.foster_id
                status += f"- **{b_id}** (Linked to <@{owner}>): {bot.battery}% Bat\n"
            return { "response": status, "state_update": generic_state }

        dynamic_prompt = f"{self.system_prompt}\nSTATUS: Oxygen {game_data.oxygen}%"
        ai_response = await tools.ai.generate_response(
            system_prompt=dynamic_prompt,
            conversation_id=generic_state.get('id'), 
            user_input=user_input
        )
        
        generic_state['metadata'] = game_data.model_dump()
        return { "response": ai_response, "state_update": generic_state }
