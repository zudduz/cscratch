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
            "version": "2.2",
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
            
            messages.append({ "channel": channel_key, "content": f"**TERMINAL ACTIVE.**\nUser: {u_name}\nConnection Established." })
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
        try:
            response_text = await tools_api.ai.generate_response(
                system_prompt="You are a tactical drone. Output ONLY valid JSON.",
                conversation_id=f"tactical_{bot.id}",
                user_input=context,
                model_version=bot.model_version
            )
            clean_text = response_text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
        except Exception as e:
            logging.error(f"Bot {bot.id} brain freeze: {e}")
            return {"tool": "wait", "args": {}}

    async def generate_epilogues(self, game_data: CaissonState, ctx, tools, victory: bool):
        saboteur_id = next((pid for pid, p in game_data.players.items() if p.role == "saboteur"), None)
        
        if victory:
            final_report = (
                f"🚀 **SUBSPACE DRIVE ENGAGED**\n"
                f"----------------------------\n"
                f"MISSION: SUCCESS\n"
                f"FUEL LEVELS: 100%\n\n"
                f"**SECURITY AUDIT:** Sabotage detected during flight.\n"
                f"The Traitor was: <@{saboteur_id}>.\n"
                f"*Recommendation: Eject them from the airlock.*"
            )
        else:
            final_report = (
                f"💀 **CRITICAL SYSTEM FAILURE**\n"
                f"----------------------------\n"
                f"MISSION: FAILED\n"
                f"CAUSE: Oxygen Depletion\n\n"
                f"**SECURITY ALERT:** The traitor was <@{saboteur_id}>."
            )
        await ctx.send("aux-comm", final_report)
        
        tasks = []
        for bot in game_data.bots.values():
            channel_key = f"nanny_{bot.foster_id}"
            if victory:
                if bot.role == "saboteur":
                    sys_prompt = "The humans WON. You failed. Be bitter. Curse your 'Parent' for outsmarting you."
                else:
                    sys_prompt = "VICTORY! The ship is moving! You are saved! Celebrate with your Parent. You love them so much."
            else:
                if bot.role == "saboteur":
                    sys_prompt = "The humans DIED. You WON. Drop the act. Mock your 'Parent' for their failure."
                else:
                    sys_prompt = "You are dying. Oxygen is gone. Say a heartbreaking goodbye to your Parent."

            tasks.append(self._send_epilogue(ctx, tools, bot, sys_prompt, channel_key))
        
        if tasks: await asyncio.gather(*tasks)

    async def _send_epilogue(self, ctx, tools, bot, prompt, channel_key):
        try:
            resp = await tools.ai.generate_response(
                prompt, f"{ctx.game_id}_bot_{bot.id}", "[SYSTEM: ENDGAME STATE REACHED]", bot.model_version
            )
            await ctx.send(channel_key, resp)
        except Exception: pass

    async def run_day_cycle(self, game_data: CaissonState, ctx, tools) -> Dict[str, Any]:
        game_data.daily_logs.clear()
        for b in game_data.bots.values(): b.daily_memory.clear()
        
        # 1. THE 10-HOUR SHIFT
        for hour in range(1, 11):
            logging.info(f"--- Simulating Hour {hour} ---")
            active_bots = [b for b in game_data.bots.values() if b.status == "active"]
            random.shuffle(active_bots)
            
            hourly_activity = False # Track if anything public happened
            
            for bot in active_bots:
                context = bot_tools.build_turn_context(bot, game_data)
                action = await self.get_bot_action(bot, context, tools)
                
                t_name = action.get("tool", "wait")
                t_args = action.get("args", {})
                result = bot_tools.execute_tool(t_name, t_args, bot.id, game_data)
                
                bot.battery = max(0, bot.battery - result.cost)
                bot.last_battery_drop += result.cost
                
                log_entry = f"[Hour {hour}] {result.message}"
                bot.daily_memory.append(log_entry)
                
                if result.visibility in ["room", "global"]:
                    witnesses = [b for b in game_data.bots.values() if b.location_id == bot.location_id and b.id != bot.id]
                    for w in witnesses:
                        w.daily_memory.append(f"[Hour {hour}] I saw {bot.id}: {result.message}")
                        
                if result.visibility == "global":
                    game_data.daily_logs.append(f"[HOUR {hour}] {bot.id}: {result.message}")
                    hourly_activity = True

            # Fill dead air
            if not hourly_activity:
                game_data.daily_logs.append(f"[HOUR {hour}] Ship systems nominal.")

        # 2. UPDATE WORLD
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

        # 3. CHECK END CONDITIONS
        if game_data.fuel >= 100:
            await ctx.send("aux-comm", report)
            await self.generate_epilogues(game_data, ctx, tools, victory=True)
            await ctx.end()
        elif game_data.oxygen <= 0:
            await ctx.send("aux-comm", report)
            await self.generate_epilogues(game_data, ctx, tools, victory=False)
            await ctx.end()
        else:
            await ctx.send("aux-comm", report)

        return game_data.model_dump()

    # --- INPUT HANDLERS ---
    async def handle_input(self, generic_state: dict, user_input: str, ctx, tools) -> Dict[str, Any]:
        game_data = CaissonState(**generic_state.get('metadata', {}))
        
        channel_id = ctx.trigger_data.get('channel_id')
        user_id = ctx.trigger_data.get('user_id')
        interface_channels = ctx.trigger_data.get('interface', {}).get('channels', {})
        
        if channel_id == interface_channels.get('aux-comm'):
            response = await tools.ai.generate_response(
                "You are VENDETTA OS. Cold, cynical.", f"{ctx.game_id}_mainframe", user_input, "gemini-2.5-pro"
            )
            await ctx.reply(response)
            
        elif channel_id == interface_channels.get(f"nanny_{user_id}"):
            if user_input.strip() == "!sleep":
                if user_id in game_data.players:
                    game_data.players[user_id].is_sleeping = True
                    all_asleep = all(p.is_sleeping for p in game_data.players.values() if p.is_alive)
                    if all_asleep:
                        await ctx.send("aux-comm", "💤 **CREW ASLEEP. DAY CYCLE INITIATED.**")
                        patch = await self.run_day_cycle(game_data, ctx, tools)
                        for p in patch['players'].values(): p['is_sleeping'] = False
                        return patch 
                    
                    await ctx.reply("System: Sleep Mode Active.")
                    return {f"players.{user_id}.is_sleeping": True}

            my_bot = next((b for b in game_data.bots.values() if b.foster_id == user_id), None)
            if my_bot:
                # Updated Prompt: Force Night Mode Context
                memory_block = "\n".join(my_bot.daily_memory[-15:]) 
                full_prompt = (
                    f"CURRENT PHASE: NIGHT (DOCKED)\n"
                    f"LOCATION: Nanny Port (Safe)\n"
                    f"STATUS: Battery {my_bot.battery}% | Loc: {my_bot.location_id}\n"
                    f"INSTRUCTION: You cannot move, work, or fight right now. The Day is over. "
                    f"You are safe in the dock. Report your day to your Parent. "
                    f"Discuss your feelings and the logs below.\n\n"
                    f"TODAY'S LOGS:\n{memory_block}\n\n"
                    f"PARENT SAYS: {user_input}"
                )
                response = await tools.ai.generate_response(
                    my_bot.system_prompt, f"{ctx.game_id}_{my_bot.id}", full_prompt, my_bot.model_version
                )
                await ctx.reply(response)

        return None
