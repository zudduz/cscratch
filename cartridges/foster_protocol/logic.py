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

    async def on_game_start(self, generic_state: dict) -> Dict[str, Any]:
        """
        Called on Game Start.
        Returns: { "metadata": updated_state, "channel_ops": [instructions] }
        """
        game_data = CaissonState(**generic_state.get('metadata', {}))
        discord_players = generic_state.get('players', [])
        
        if not discord_players:
            return { "metadata": game_data.model_dump() }

        # 1. Assign Roles
        saboteur_index = random.randint(0, len(discord_players) - 1)
        channel_ops = []

        # 2. Request Public Channel (The Picnic)
        channel_ops.append({
            "op": "create",
            "key": "picnic",
            "name": "picnic",
            "audience": "public",
            "init_msg": "**MAINFRAME ONLINE.**\n*System Clock: Cycle 1*\n*Status: Emergency Power Only.*"
        })

        # 3. Generate Entities & Channels
        for i, p_data in enumerate(discord_players):
            u_id = p_data['id']
            u_name = p_data['name']
            
            is_saboteur = (i == saboteur_index)
            role = "saboteur" if is_saboteur else "loyal"
            
            # Request Private Nanny Port
            channel_key = f"nanny_{u_id}"
            
            channel_ops.append({
                "op": "create",
                "key": channel_key,
                "name": f"nanny-port-{u_name}",
                "audience": "private",
                "user_id": u_id,
                "init_msg": f"**CONNECTION ESTABLISHED**\nUser: {u_name}\nSubject: [Scanning...]"
            })

            # Create PlayerState
            game_data.players[u_id] = PlayerState(role=role)
            
            # --- NEW: Random Unique Bot ID ---
            while True:
                # Generate random 3-digit suffix (000-999)
                suffix = f"{random.randint(0, 999):03d}"
                bot_id = f"unit_{suffix}"
                
                # Ensure uniqueness in this lobby
                if bot_id not in game_data.bots:
                    break
            
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
            
            game_data.daily_logs.append(f"SYSTEM: {bot_id} came online.")

        # 4. Save & Return
        return {
            "metadata": game_data.model_dump(),
            "channel_ops": channel_ops
        }

    async def handle_input(self, generic_state: dict, user_input: str, context: dict, tools) -> Dict[str, Any]:
        game_data = CaissonState(**generic_state.get('metadata', {}))
        
        # Determine Context
        channel_id = context.get('channel_id')
        user_id = context.get('user_id')
        interface_channels = context.get('interface', {}).get('channels', {})
        
        # Is this the Picnic?
        picnic_id = interface_channels.get('picnic')
        is_picnic = (channel_id == picnic_id)
        
        # Is this a Nanny Port?
        user_nanny_key = f"nanny_{user_id}"
        user_nanny_id = interface_channels.get(user_nanny_key)
        is_nanny = (channel_id == user_nanny_id)

        # --- LOGIC BRANCHING ---
        response_text = None

        if is_picnic:
            # Mainframe Logic
            if "status" in user_input.lower():
                response_text = f"**MAINFRAME v9.0**\nOXYGEN: {game_data.oxygen}% | FUEL: {game_data.fuel}%"
            else:
                response_text = await tools.ai.generate_response(
                    system_prompt="You are the Ship Computer. You are cold and cynical.",
                    conversation_id=f"{generic_state['id']}_mainframe",
                    user_input=user_input
                )

        elif is_nanny:
            # Bot Logic
            my_bot = None
            for b in game_data.bots.values():
                if b.foster_id == user_id:
                    my_bot = b
                    break
            
            if my_bot:
                # Use the Bot's Persona
                response_text = await tools.ai.generate_response(
                    system_prompt=my_bot.system_prompt,
                    conversation_id=f"{generic_state['id']}_bot_{my_bot.id}",
                    user_input=user_input
                )
            else:
                response_text = "ERROR: No Unit bonded to this terminal."

        else:
            response_text = "Transmission unclear."

        # Save State
        generic_state['metadata'] = game_data.model_dump()
        return { 
            "response": response_text, 
            "state_update": generic_state 
        }
