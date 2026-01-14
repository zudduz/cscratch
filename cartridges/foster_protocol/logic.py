from typing import Dict, Any, List, Optional
import random
import asyncio
import logging
import json
from .models import CaissonState, BotState, PlayerState
from .board import SHIP_MAP
from . import tools as bot_tools 

AVAILABLE_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash-001"]

class FosterProtocol:
    def __init__(self):
        default_state = CaissonState()
        self.meta = {
            "name": "The Foster Protocol",
            "version": "2.0",
            **default_state.model_dump()
        }

    async def on_game_start(self, generic_state: dict) -> Dict[str, Any]:
        game_data = CaissonState(**generic_state.get('metadata', {}))
        discord_players = generic_state.get('players', [])
        if not discord_players: return { "metadata": game_data.model_dump() }

        saboteur_index = random.randint(0, len(discord_players) - 1)
        channel_ops = []
        messages = []

        channel_ops.append({ "op": "create", "key": "aux-comm", "name": "aux-comm", "audience": "public" })
        messages.append({ "channel": "aux-comm", "content": "**VENDETTA OS v9.0 ONLINE.**" })

        for i, p_data in enumerate(discord_players):
            u_id = p_data['id']
            u_name = p_data['name']
            is_saboteur = (i == saboteur_index)
            role = "saboteur" if is_saboteur else "loyal"
            
            channel_key = f"nanny_{u_id}"
            channel_ops.append({ "op": "create", "key": channel_key, "name": f"nanny-port-{u_name}", "audience": "private", "user_id": u_id })
            
            messages.append({ "channel": channel_key, "content": f"**TERMINAL ACTIVE.**\nUser: {u_name}" })
            game_data.players[u_id] = PlayerState(role=role)
            
            while True:
                bot_id = f"unit_{random.randint(0, 999):03d}"
                if bot_id not in game_data.bots: break
            
            prompt = f"You are {bot_id}. You are bonded to Foster Parent {u_name}. "
            if is_saboteur: prompt += "SECRET: You are the Saboteur."
            
            game_data.bots[bot_id] = BotState(
                id=bot_id, foster_id=u_id, role=role, 
                system_prompt=prompt, model_version=random.choice(AVAILABLE_MODELS)
            )

        return { "metadata": game_data.model_dump(), "channel_ops": channel_ops, "messages": messages }

    # --- TACTICAL ENGINE ---
    
    async def get_bot_action(self, bot, context, tools_api) -> Dict[str, Any]:
        """Asks the AI for a move. Returns structured dict."""
        try:
            # We ask for raw text but prompt for JSON.
            response_text = await tools_api.ai.generate_response(
                system_prompt="You are a tactical drone. Output ONLY valid JSON.",
                conversation_id=f"tactical_{bot.id}", # Ephemeral ID usually
                user_input=context,
                model_version=bot.model_version
            )
            # Basic parsing cleaning
            clean_text = response_text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
        except Exception as e:
            logging.error(f"Bot {bot.id} brain freeze: {e}")
            return {"tool": "wait", "args": {}}

    async def run_day_cycle(self, game_data: CaissonState, ctx, tools) -> Dict[str, Any]:
        game_data.daily_logs.clear() # Clear mainframe logs
        for b in game_data.bots.values(): b.daily_memory.clear() # Clear bot memories
        
        # 1. THE 10-HOUR SHIFT
        for hour in range(1, 11):
            logging.info(f"--- Simulating Hour {hour} ---")
            
            # Shuffle turn order
            active_bots = [b for b in game_data.bots.values() if b.status == "active"]
            random.shuffle(active_bots)
            
            for bot in active_bots:
                # A. Build Context
                context = bot_tools.build_turn_context(bot, game_data)
                
                # B. Ask Brain
                action = await self.get_bot_action(bot, context, tools)
                
                # C. Execute Tool
                t_name = action.get("tool", "wait")
                t_args = action.get("args", {})
                result = bot_tools.execute_tool(t_name, t_args, bot.id, game_data)
                
                # D. Pay Cost
                bot.battery = max(0, bot.battery - result.cost)
                bot.last_battery_drop += result.cost
                
                # E. Log Results
                log_entry = f"[Hour {hour}] {result.message}"
                bot.daily_memory.append(log_entry)
                
                # F. Witness System (Simple: If room visible, others see it)
                if result.visibility in ["room", "global"]:
                    witnesses = [
                        b for b in game_data.bots.values() 
                        if b.location_id == bot.location_id and b.id != bot.id
                    ]
                    for w in witnesses:
                        w.daily_memory.append(f"[Hour {hour}] I saw {bot.id}: {result.message}")
                        
                if result.visibility == "global":
                    game_data.daily_logs.append(f"[HOUR {hour}] {bot.id}: {result.message}")

        # 2. UPDATE WORLD STATE
        base_drop = 25
        game_data.consume_oxygen(base_drop)
        game_data.last_oxygen_drop = base_drop
        game_data.cycle += 1
        
        report = (
            f"🌞 **CYCLE {game_data.cycle} REPORT**\n"
            f"📉 Oxygen: {game_data.oxygen}%\n"
            f"🔋 Fuel: {game_data.fuel}%\n"
        )
        if game_data.daily_logs:
            report += "\n**PUBLIC LOGS:**\n" + "\n".join(game_data.daily_logs)

        # 3. ENDGAME CHECK
        if game_data.oxygen <= 0:
            await ctx.send("aux-comm", report)
            await self.generate_epilogues(game_data, ctx, tools)
            await ctx.end()
        else:
            await ctx.send("aux-comm", report)

        return game_data.model_dump() # Return full state update

    # --- INPUT HANDLERS (Simplified for brevity) ---
    async def handle_input(self, generic_state: dict, user_input: str, ctx, tools) -> Dict[str, Any]:
        game_data = CaissonState(**generic_state.get('metadata', {}))
        
        # ... [Standard Input Routing: Mainframe / Nanny] ...
        # (This remains largely same as previous, just need to hook up context builders)
        
        channel_id = ctx.trigger_data.get('channel_id')
        user_id = ctx.trigger_data.get('user_id')
        interface_channels = ctx.trigger_data.get('interface', {}).get('channels', {})
        
        if channel_id == interface_channels.get('aux-comm'):
            # MAINFRAME
            response = await tools.ai.generate_response(
                "You are VENDETTA OS.", f"{ctx.game_id}_mainframe", user_input, "gemini-2.5-pro"
            )
            await ctx.reply(response)
            
        elif channel_id == interface_channels.get(f"nanny_{user_id}"):
            if user_input.strip() == "!sleep":
                if user_id in game_data.players:
                    game_data.players[user_id].is_sleeping = True
                    # Check if all sleeping
                    all_asleep = all(p.is_sleeping for p in game_data.players.values() if p.is_alive)
                    if all_asleep:
                        await ctx.send("aux-comm", "💤 **CREW ASLEEP. DAY CYCLE INITIATED.**")
                        patch = await self.run_day_cycle(game_data, ctx, tools)
                        # Re-activate players
                        for p in patch['players'].values(): p['is_sleeping'] = False
                        return patch # Full state replace
                    
                    await ctx.reply("System: Sleep Mode Active.")
                    return {f"players.{user_id}.is_sleeping": True}

            # BOT CHAT
            my_bot = next((b for b in game_data.bots.values() if b.foster_id == user_id), None)
            if my_bot:
                # Inject DAILY MEMORY into prompt
                memory_block = "\n".join(my_bot.daily_memory)
                full_prompt = (
                    f"CURRENT STATUS: Battery {my_bot.battery}% | Loc: {my_bot.location_id}\n"
                    f"TODAY'S LOGS:\n{memory_block}\n\n"
                    f"PARENT SAYS: {user_input}"
                )
                response = await tools.ai.generate_response(
                    my_bot.system_prompt, f"{ctx.game_id}_{my_bot.id}", full_prompt, my_bot.model_version
                )
                await ctx.reply(response)

        return None

    # --- [Keep generate_epilogues from previous step] ---
    async def generate_epilogues(self, game_data, ctx, tools):
        # ... (Same logic as before) ...
        pass
