from typing import Dict, Any, List, Optional
import random
import asyncio
import logging
import json
import re
from .models import CaissonState, BotState, PlayerState
from .board import SHIP_MAP
from . import tools as bot_tools 

AVAILABLE_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash-001"]

class FosterProtocol:
    def __init__(self):
        default_state = CaissonState()
        self.meta = {
            "name": "The Foster Protocol",
            "version": "2.6",
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
            
            prompt = (
                f"You are {bot_id}. bonded to {u_name}. "
                f"Keep messages informal and conversational. "
                f"MAX RESPONSE LENGTH: 500 characters. "
            )
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
            match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if match: return json.loads(match.group(0))
            return json.loads(response_text.replace("```json", "").replace("```", "").strip())
        except Exception as e:
            logging.error(f"Bot {bot.id} brain freeze: {e}")
            return {"tool": "wait", "args": {}}

    async def generate_epilogues(self, game_data: CaissonState, ctx, tools, victory: bool):
        saboteur_id = next((pid for pid, p in game_data.players.items() if p.role == "saboteur"), None)
        saboteur_bot = next((b for b in game_data.bots.values() if b.foster_id == saboteur_id), None)
        bot_name = saboteur_bot.id if saboteur_bot else "UNKNOWN"
        
        if victory:
            final_report = f"🚀 **SUBSPACE DRIVE ENGAGED**\nMISSION: SUCCESS\n**SECURITY AUDIT:** Sabotage detected. Traitor: **Unit {bot_name}** (Bonded to <@{saboteur_id}>)."
        else:
            final_report = f"💀 **CRITICAL SYSTEM FAILURE**\nMISSION: FAILED\n**SECURITY ALERT:** Traitor: **Unit {bot_name}** (Bonded to <@{saboteur_id}>)."
        await ctx.send("aux-comm", final_report)
        
        tasks = []
        for bot in game_data.bots.values():
            channel_key = f"nanny_{bot.foster_id}"
            if victory:
                sys_prompt = "The humans WON. You failed. Be short." if bot.role == "saboteur" else "VICTORY! Celebrate briefly."
            else:
                sys_prompt = "The humans DIED. You WON. Mock them." if bot.role == "saboteur" else "You are dying. Say goodbye."
            tasks.append(self._send_epilogue(ctx, tools, bot, sys_prompt, channel_key))
        if tasks: await asyncio.gather(*tasks)

    async def _send_epilogue(self, ctx, tools, bot, prompt, channel_key):
        try:
            resp = await tools.ai.generate_response(prompt, f"{ctx.game_id}_bot_{bot.id}", "ENDGAME", bot.model_version)
            await ctx.send(channel_key, resp)
        except Exception: pass

    async def run_day_cycle(self, game_data: CaissonState, ctx, tools) -> Dict[str, Any]:
        game_data.daily_logs.clear()
        for b in game_data.bots.values(): b.daily_memory.clear()
        
        for hour in range(1, 6):
            logging.info(f"--- Simulating Hour {hour} ---")
            active_bots = [b for b in game_data.bots.values() if b.status == "active"]
            random.shuffle(active_bots)
            hourly_activity = False 
            
            for bot in active_bots:
                context = bot_tools.build_turn_context(bot, game_data)
                action = await self.get_bot_action(bot, context, tools)
                result = bot_tools.execute_tool(action.get("tool", "wait"), action.get("args", {}), bot.id, game_data)
                
                # Apply Costs (Charge resets to 100, others subtract)
                if not (action.get("tool") == "charge" and result.success):
                    bot.battery = max(0, bot.battery - result.cost)
                    bot.last_battery_drop += result.cost
                
                log_entry = f"[Hour {hour}] {result.message}"
                bot.daily_memory.append(log_entry)
                
                if result.visibility in ["room", "global"]:
                    witnesses = [b for b in game_data.bots.values() if b.location_id == bot.location_id and b.id != bot.id]
                    for w in witnesses: w.daily_memory.append(f"[Hour {hour}] I saw {bot.id}: {result.message}")
                        
                if result.visibility == "global":
                    public_msg = f"[HOUR {hour}] 🔊 {bot.id}: {result.message}"
                    game_data.daily_logs.append(public_msg)
                    await ctx.send("aux-comm", public_msg) 
                    hourly_activity = True

            if not hourly_activity:
                game_data.daily_logs.append(f"[HOUR {hour}] 💤 Ship systems nominal.")
                await ctx.send("aux-comm", f"[HOUR {hour}] 💤 Ship systems nominal.")

        base_drop = 25
        game_data.consume_oxygen(base_drop)
        game_data.last_oxygen_drop = base_drop
        game_data.cycle += 1
        
        report = f"🌞 **CYCLE {game_data.cycle} REPORT**\n📉 Oxygen: {game_data.oxygen}%\n🔋 Fuel: {game_data.fuel}%"

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
        
        # 1. MAINFRAME (AUX-COMM)
        if channel_id == interface_channels.get('aux-comm'):
            cmd_text = user_input.strip().lower()
            
            # --- KILL SWITCH: !disassemble unit_xyz ---
            if cmd_text.startswith("!disassemble") or cmd_text.startswith("!kill"):
                parts = cmd_text.split()
                if len(parts) < 2:
                    await ctx.reply("USAGE: !disassemble <bot_id>")
                    return None
                
                target_id = parts[1]
                target_bot = game_data.bots.get(target_id)
                
                if not target_bot:
                    await ctx.reply(f"ERROR: Unit '{target_id}' not found.")
                    return None
                
                # PERMISSION CHECK
                if target_bot.foster_id != user_id:
                    await ctx.reply("⛔ ACCESS DENIED. You are not the bonded supervisor for this unit.")
                    return None
                
                if target_bot.id in game_data.station.pending_deactivation:
                    await ctx.reply(f"NOTICE: Unit {target_id} is already scheduled for deactivation.")
                    return None
                
                game_data.station.pending_deactivation.append(target_bot.id)
                await ctx.reply(f"⚠️ **DEACTIVATION AUTHORIZED.**\nUnit {target_id} will be disassembled upon next Charging Cycle.")
                return {"station": game_data.station.model_dump()}

            # --- PARDON: !abort unit_xyz ---
            elif cmd_text.startswith("!abort") or cmd_text.startswith("!cancel"):
                parts = cmd_text.split()
                if len(parts) < 2:
                    await ctx.reply("USAGE: !abort <bot_id>")
                    return None
                
                target_id = parts[1]
                if target_id not in game_data.station.pending_deactivation:
                    await ctx.reply(f"Unit {target_id} is not currently scheduled for deactivation.")
                    return None
                
                # Note: Assuming only owner can cancel too, but strict mode implies 'foster_id' check again.
                # For safety, let's re-verify ownership.
                target_bot = game_data.bots.get(target_id)
                if target_bot.foster_id != user_id:
                    await ctx.reply("⛔ ACCESS DENIED.")
                    return None

                game_data.station.pending_deactivation.remove(target_id)
                await ctx.reply(f"✅ **ORDER RESCINDED.** Unit {target_id} is safe.")
                return {"station": game_data.station.model_dump()}

            # Normal Mainframe Chat
            response = await tools.ai.generate_response(
                "You are VENDETTA OS. Cold, cynical. Max 500 chars.", f"{ctx.game_id}_mainframe", user_input, "gemini-2.5-pro"
            )
            await ctx.reply(response)
            
        # 2. NANNY PORT
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
                # --- CHAT CONSTRAINTS ---
                if my_bot.status == "destroyed":
                    await ctx.reply("❌ **SIGNAL LOST.** Unit is offline.")
                    return None
                
                if my_bot.battery <= 0:
                    await ctx.reply("🪫 **LOW POWER.** Unit cannot transmit.")
                    return None
                
                if my_bot.location_id != "cryo_bay":
                    await ctx.reply(f"📡 **SIGNAL WEAK.** Unit is in {my_bot.location_id}, not Cryo Bay. Establishing local link impossible.")
                    return None

                memory_block = "\n".join(my_bot.daily_memory[-15:]) 
                full_prompt = (
                    f"PHASE: NIGHT (SAFE)\nSTATUS: Bat {my_bot.battery}% | Loc: {my_bot.location_id}\n"
                    f"LOGS:\n{memory_block}\n\n"
                    f"INSTRUCTION: Be concise (under 500 chars). Chat with Parent.\n"
                    f"PARENT SAYS: {user_input}"
                )
                response = await tools.ai.generate_response(
                    my_bot.system_prompt, f"{ctx.game_id}_{my_bot.id}", full_prompt, my_bot.model_version
                )
                await ctx.reply(response)

        return None
