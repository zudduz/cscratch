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
            
            # Random Bot ID
            while True:
                suffix = f"{random.randint(0, 999):03d}"
                bot_id = f"unit_{suffix}"
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

    async def run_day_cycle(self, game_data: CaissonState) -> str:
        """
        Executes the Day Phase simulation.
        Future: This will be where we await AI agent tools.
        Current: Decrements oxygen.
        """
        # 1. Increment Cycle
        game_data.cycle += 1
        
        # 2. Consume Resources (Simple Logic)
        old_o2 = game_data.oxygen
        game_data.oxygen = int(game_data.oxygen * 0.75) # Reduce by 25%
        loss = old_o2 - game_data.oxygen
        
        # 3. Reset Players
        for p in game_data.players.values():
            p.is_sleeping = False

        # 4. Generate Report
        report = (
            f"🌞 **CYCLE {game_data.cycle} STARTED**\n"
            f"----------------------------------\n"
            f"📉 **Oxygen Levels:** {game_data.oxygen}% (Dropped {loss}%)\n"
            f"🔋 **Ship Power:** Stable\n"
            f"----------------------------------\n"
            f"*Crew awake. Nanny Ports active.*"
        )
        game_data.daily_logs.append(f"CYCLE {game_data.cycle}: Oxygen dropped to {game_data.oxygen}%.")
        
        return report

    async def handle_input(self, generic_state: dict, user_input: str, context: dict, tools) -> Dict[str, Any]:
        game_data = CaissonState(**generic_state.get('metadata', {}))
        
        # Determine Context
        channel_id = context.get('channel_id')
        user_id = context.get('user_id')
        interface_channels = context.get('interface', {}).get('channels', {})
        
        picnic_id = interface_channels.get('picnic')
        is_picnic = (channel_id == picnic_id)
        
        user_nanny_key = f"nanny_{user_id}"
        user_nanny_id = interface_channels.get(user_nanny_key)
        is_nanny = (channel_id == user_nanny_id)

        response_text = None
        channel_ops = None

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
            # --- SLEEP COMMAND ---
            if user_input.strip().lower() == "!sleep":
                # 1. Update Sleep State
                if user_id in game_data.players:
                    game_data.players[user_id].is_sleeping = True
                
                # 2. Check Global State
                living_players = [p for p in game_data.players.values() if p.is_alive]
                sleeping_count = sum(1 for p in living_players if p.is_sleeping)
                total_living = len(living_players)
                
                # 3. Formulate Response
                response_text = f"**CRYO-SLEEP CONFIRMED.**\n*Vitals stabilizing...*\n\n"
                response_text += f"**Crew Asleep:** {sleeping_count}/{total_living}"
                
                if sleeping_count >= total_living:
                    response_text += "\n\n🚨 **ALL CREW ASLEEP.**\n*Simulating Day Cycle...*"
                    
                    # --- TRIGGER DAY CYCLE ---
                    day_report = await self.run_day_cycle(game_data)
                    
                    # We want to post this report to the PUBLIC channel (Picnic)
                    # Currently handle_input returns a response to the *current* channel.
                    # We can use 'channel_ops' to send a message to a specific channel key!
                    
                    # Let's add a 'message' op to our protocol?
                    # Or simpler: The return value 'response' goes to the user, 
                    # but we overwrite the return text to be the report if it's the last person?
                    # Actually, the report should go to #picnic.
                    
                    # NOTE: Our discord_client currently only supports 'create'/'delete' ops.
                    # Let's hack it: Return the report as the response to the LAST person who slept.
                    # They are effectively the one "turning off the lights".
                    
                    response_text += f"\n\n{day_report}"
            
            else:
                # Normal Bot Chat
                my_bot = None
                for b in game_data.bots.values():
                    if b.foster_id == user_id:
                        my_bot = b
                        break
                
                if my_bot:
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
        
        result = { 
            "response": response_text, 
            "state_update": generic_state 
        }
        if channel_ops:
            result['channel_ops'] = channel_ops
            
        return result
