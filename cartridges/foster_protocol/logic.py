from typing import Dict, Any, List, Optional
import random
import asyncio
from .models import CaissonState, BotState, PlayerState
from .board import SHIP_MAP

class FosterProtocol:
    def __init__(self):
        default_state = CaissonState()
        self.meta = {
            "name": "The Foster Protocol",
            "description": "A social deduction game aboard a dying starship.",
            "version": "1.5",
            **default_state.model_dump()
        }
        self.system_prompt = """
        ROLE: You are the Game Master for 'The Foster Protocol'.
        """

    async def on_game_start(self, generic_state: dict) -> Dict[str, Any]:
        game_data = CaissonState(**generic_state.get('metadata', {}))
        discord_players = generic_state.get('players', [])
        
        if not discord_players: return { "metadata": game_data.model_dump() }

        saboteur_index = random.randint(0, len(discord_players) - 1)
        channel_ops = []
        messages = []

        channel_ops.append({ "op": "create", "key": "picnic", "name": "picnic", "audience": "public" })
        messages.append({ "channel": "picnic", "content": "**MAINFRAME ONLINE.**\n*Cycle 1*" })

        for i, p_data in enumerate(discord_players):
            u_id = p_data['id']
            u_name = p_data['name']
            is_saboteur = (i == saboteur_index)
            role = "saboteur" if is_saboteur else "loyal"
            
            channel_key = f"nanny_{u_id}"
            channel_ops.append({
                "op": "create", "key": channel_key, "name": f"nanny-port-{u_name}",
                "audience": "private", "user_id": u_id
            })
            messages.append({ "channel": channel_key, "content": f"**CONNECTED:** {u_name}" })

            game_data.players[u_id] = PlayerState(role=role)
            
            while True:
                bot_id = f"unit_{random.randint(0, 999):03d}"
                if bot_id not in game_data.bots: break
            
            prompt = f"You are {bot_id}. You serve {u_name}."
            if is_saboteur: prompt += " You are the Saboteur."
            
            game_data.bots[bot_id] = BotState(
                id=bot_id, foster_id=u_id, role=role, 
                system_prompt=prompt, goal_summary="Survive."
            )

        return {
            "metadata": game_data.model_dump(),
            "channel_ops": channel_ops,
            "messages": messages
        }

    async def task_perform_scan(self, ctx, channel_key: str):
        await asyncio.sleep(3)
        await ctx.send(channel_key, "📡 **SCAN COMPLETE:**\n*No anomalies detected.*")
        return None 

    async def run_day_cycle(self, game_data: CaissonState, ctx) -> Dict[str, Any]:
        new_cycle = game_data.cycle + 1
        new_oxygen = max(0, game_data.oxygen - 25)
        loss = game_data.oxygen - new_oxygen
        
        report = (
            f"🌞 **CYCLE {new_cycle} REPORT**\n"
            f"📉 Oxygen: {new_oxygen}% (-{loss})\n"
            f"*Crew awake.*"
        )
        
        patch = {
            "cycle": new_cycle,
            "oxygen": new_oxygen
        }
        
        for pid in game_data.players:
            patch[f"players.{pid}.is_sleeping"] = False
            
        # GAME OVER CHECK
        if new_oxygen <= 0:
            report += "\n\n💀 **CRITICAL FAILURE: LIFE SUPPORT OFFLINE.**\n*The simulation has ended.*"
            await ctx.send("picnic", report)
            await ctx.end() # Freezes the game
        else:
            await ctx.send("picnic", report)

        return patch

    async def handle_input(self, generic_state: dict, user_input: str, ctx, tools) -> Dict[str, Any]:
        game_data = CaissonState(**generic_state.get('metadata', {}))
        
        channel_id = ctx.trigger_data.get('channel_id')
        user_id = ctx.trigger_data.get('user_id')
        interface_channels = ctx.trigger_data.get('interface', {}).get('channels', {})
        
        picnic_id = interface_channels.get('picnic')
        is_picnic = (channel_id == picnic_id)
        
        user_nanny_key = f"nanny_{user_id}"
        user_nanny_id = interface_channels.get(user_nanny_key)
        is_nanny = (channel_id == user_nanny_id)

        if is_picnic:
            if "status" in user_input.lower():
                await ctx.reply(f"**MAINFRAME:** O2: {game_data.oxygen}% | FUEL: {game_data.fuel}%")
                return None
            else:
                response = await tools.ai.generate_response(
                    system_prompt="You are the Ship Computer. Cold, cynical.",
                    conversation_id=f"{ctx.game_id}_mainframe",
                    user_input=user_input
                )
                await ctx.reply(response)
                return None

        elif is_nanny:
            cmd = user_input.strip().lower()
            
            if cmd == "!scan":
                await ctx.reply("🔭 **SCANNER ACTIVATED.**")
                ctx.spawn(self.task_perform_scan(ctx, user_nanny_key))
                return None

            elif cmd == "!sleep":
                if user_id in game_data.players:
                    game_data.players[user_id].is_sleeping = True
                    living = [p for p in game_data.players.values() if p.is_alive]
                    sleeping_count = sum(1 for p in living if p.is_sleeping)
                    total = len(living)
                    
                    await ctx.reply(f"**SLEEPING.** ({sleeping_count}/{total})")
                    patch = {f"players.{user_id}.is_sleeping": True}
                    
                    if sleeping_count >= total:
                        await ctx.send("picnic", "🚨 **ALL CREW ASLEEP.**")
                        day_patch = await self.run_day_cycle(game_data, ctx)
                        patch.update(day_patch)
                    return patch

            else:
                my_bot = next((b for b in game_data.bots.values() if b.foster_id == user_id), None)
                if my_bot:
                    response = await tools.ai.generate_response(
                        system_prompt=my_bot.system_prompt,
                        conversation_id=f"{ctx.game_id}_bot_{my_bot.id}",
                        user_input=user_input
                    )
                    await ctx.reply(response)
                else:
                    await ctx.reply("ERROR: No Unit bonded.")
                return None

        return None
