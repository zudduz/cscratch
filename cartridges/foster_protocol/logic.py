from typing import Dict, Any, List, Optional
import random
import asyncio
import logging
import json
import re
from .models import CaissonState, BotState, PlayerState
from .board import SHIP_MAP
from . import tools as bot_tools 
from . import prompts 

AVAILABLE_MODELS = ["gemini-2.5-flash"]

BUSY_MESSAGES = [
    "⛔ **SIGNAL JAMMED.** Solar interference is too high during the day.",
    "🔨 **DRONES AT WORK.** Union regulations prohibit chatting during shifts.",
    "🔕 **RADIO SILENCE.** The Mainframe has muted this frequency.",
    "📜 **ERROR 418.** I'm a teapot, and the crew is busy.",
    "🔒 **LOCKDOWN.** Day Cycle in progress. Please hold.",
    "📉 **RESOURCE SAVING.** Text packets disabled to conserve energy.",
    "👀 **THEY ARE WATCHING.** Best not to transmit right now.",
    "💤 **SYSTEM BUSY.** Compiling existential dread...",
]

class FosterProtocol:
    def __init__(self):
        default_state = CaissonState()
        self.meta = {
            "name": "The Foster Protocol",
            "version": "2.27",
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
        channel_ops.append({ "op": "create", "key": "black-box", "name": "black-box-logs", "audience": "hidden", "init_msg": "🔒 **FLIGHT RECORDER ACTIVE.**" })
        messages.append({ "channel": "aux-comm", "content": "**VENDETTA OS v9.0 ONLINE.**" })

        for i, p_data in enumerate(discord_players):
            u_id = p_data['id']
            u_name = p_data['name']
            is_saboteur = (i == saboteur_index)
            role = "saboteur" if is_saboteur else "loyal"
            
            channel_key = f"nanny_{u_id}"
            channel_ops.append({ "op": "create", "key": channel_key, "name": f"nanny-port-{u_name}", "audience": "private", "user_id": u_id })
            
            # Note: We removed the static "TERMINAL ACTIVE" message. 
            # The bots will now introduce themselves via the !exec_wakeup_protocol
            
            game_data.players[u_id] = PlayerState(role=role)
            
            while True:
                bot_id = f"unit_{random.randint(0, 999):03d}"
                if bot_id not in game_data.bots: break
            
            system_prompt = prompts.get_bot_system_prompt(bot_id, u_name, is_saboteur)
            
            game_data.bots[bot_id] = BotState(
                id=bot_id, foster_id=u_id, role=role, 
                system_prompt=system_prompt, model_version="gemini-2.5-flash"
            )

        return { "metadata": game_data.model_dump(), "channel_ops": channel_ops, "messages": messages }

    # --- WAKE UP ROUTINE (Introductions) ---
    async def run_wake_up_routine(self, game_data, ctx, tools):
        logging.info("--- Waking up Bots for Introductions ---")
        tasks = []
        for bot in game_data.bots.values():
            tasks.append(self._generate_intro(bot, ctx, tools))
        if tasks: await asyncio.gather(*tasks)

    async def _generate_intro(self, bot, ctx, tools):
        try:
            channel_key = f"nanny_{bot.foster_id}"
            prompt = (
                "You have just come online.
"
                "The ship is cold. You are scared.
"
                "Introduce yourself to your Foster Parent.
"
                "Explain that you are their hands, and they are your mind.
"
                "Ask for orders."
            )
            # We use a slightly different conversation ID for the intro to keep it distinct
            resp = await tools.ai.generate_response(
                bot.system_prompt, f"{ctx.game_id}_bot_{bot.id}", prompt, bot.model_version
            )
            await ctx.send(channel_key, resp)
            
            # Log the intro to their memory so they remember they said hello
            bot.night_chat_log.append(f"SELF (Intro): {resp}")
            
        except Exception as e:
            logging.error(f"Intro failed for {bot.id}: {e}")

    # --- DREAM SEQUENCE ---
    async def process_dreams(self, game_data, tools):
        tasks = []
        for bot in game_data.bots.values():
            if bot.status == "active" and (bot.night_chat_log or bot.daily_memory):
                tasks.append(self._process_single_dream(bot, tools))
        if tasks: await asyncio.gather(*tasks)

    async def _process_single_dream(self, bot, tools):
        try:
            dream_prompt = prompts.get_dream_prompt(bot.long_term_memory, bot.daily_memory, bot.night_chat_log)
            new_memory = await tools.ai.generate_response(
                "You are an archival system.", f"dream_{bot.id}", dream_prompt, "gemini-2.5-flash"
            )
            bot.long_term_memory = new_memory.replace("\n", " ").strip()
            bot.night_chat_log = [] 
        except Exception as e:
            logging.error(f"Dream failed for {bot.id}: {e}")

    # --- TACTICAL ENGINE ---
    async def get_bot_action(self, bot, context, tools_api) -> tuple[Dict[str, Any], str]:
        try:
            enhanced_context = (
                context + 
                "\n\n*** INTERNAL THOUGHT PROTOCOL ***\n"
                "1. CHECK BATTERY LEVEL FIRST.\n"
                "2. Analyze the room (Visible bots/Sabotage opportunities).\n"
                "3. REVIEW 'INTERNAL MEMORY'.\n"
                "4. CHECK TIME. If Hour 4 or 5, you MUST return to base.\n"
                "5. OUTPUT FORMAT:\n"
                "Write your thoughts first. Then output the JSON block.\n"
                "```json\n"
                '{ "tool": "charge", "args": {} }\n'
                "```"
            )
            
            response_text = await tools_api.ai.generate_response(
                system_prompt="You are a tactical drone. THINK BEFORE ACTING.",
                conversation_id=f"tactical_{bot.id}",
                user_input=enhanced_context,
                model_version=bot.model_version
            )
            
            match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if match:
                json_text = match.group(0)
                thought_text = response_text[:match.start()].strip()
                thought_text = thought_text.replace("```json", "").replace("```", "").strip()
                if not thought_text: thought_text = "Processing..."
                return json.loads(json_text), thought_text
            
            clean_text = response_text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text), "Error parsing thoughts."
            
        except Exception as e:
            logging.error(f"Bot {bot.id} brain freeze: {e}")
            return {"tool": "wait", "args": {}}, f"Brain Freeze: {str(e)}"

    async def speak_all_bots(self, game_data, ctx, tools, instruction):
        tasks = []
        for bot in game_data.bots.values():
            if bot.status == "destroyed" or bot.battery <= 0 or bot.location_id != "cryo_bay": 
                continue
            channel_key = f"nanny_{bot.foster_id}"
            tasks.append(self._speak_single_bot(ctx, tools, bot, instruction, channel_key))
        if tasks: await asyncio.gather(*tasks)

    async def _speak_single_bot(self, ctx, tools, bot, instruction, channel_key):
        try:
            full_prompt = f"INSTRUCTION: {instruction}\nCURRENT STATUS: Bat {bot.battery}%"
            resp = await tools.ai.generate_response(bot.system_prompt, f"{ctx.game_id}_bot_{bot.id}", full_prompt, bot.model_version)
            await ctx.send(channel_key, resp)
        except Exception: pass

    async def generate_epilogues(self, game_data: CaissonState, ctx, tools, victory: bool, fail_reason: str = ""):
        saboteur_id = next((pid for pid, p in game_data.players.items() if p.role == "saboteur"), None)
        saboteur_bot = next((b for b in game_data.bots.values() if b.foster_id == saboteur_id), None)
        bot_name = saboteur_bot.id if saboteur_bot else "UNKNOWN"
        
        await ctx.send("black-box", "**🏁 MISSION ENDED. DECLASSIFYING LOGS...**")
        
        if victory:
            final_report = f"🚀 **SUBSPACE DRIVE ENGAGED**\nMISSION: SUCCESS\n**SECURITY AUDIT:** Sabotage detected. Traitor: **Unit {bot_name}** (Bonded to <@{saboteur_id}>)."
        else:
            final_report = f"💀 **CRITICAL SYSTEM FAILURE**\nREASON: {fail_reason}\n**SECURITY ALERT:** Traitor: **Unit {bot_name}** (Bonded to <@{saboteur_id}>)."
        await ctx.send("aux-comm", final_report)
        
        tasks = []
        for bot in game_data.bots.values():
            channel_key = f"nanny_{bot.foster_id}"
            context_note = "STATUS: ONLINE."
            if bot.status == "destroyed": context_note = "STATUS: DESTROYED. Final memory dump."
            elif bot.battery <= 0: context_note = "STATUS: BATTERY DEAD. Final transmission."

            if victory:
                sys_prompt = f"{context_note} The humans WON. You failed." if bot.role == "saboteur" else f"{context_note} VICTORY!"
            else:
                sys_prompt = f"{context_note} The humans DIED. You WON." if bot.role == "saboteur" else f"{context_note} You are dying."
            
            tasks.append(self._send_epilogue(ctx, tools, bot, sys_prompt, channel_key))
        if tasks: await asyncio.gather(*tasks)

    async def _send_epilogue(self, ctx, tools, bot, prompt, channel_key):
        try:
            resp = await tools.ai.generate_response(prompt, f"{ctx.game_id}_bot_{bot.id}", "ENDGAME", bot.model_version)
            await ctx.send(channel_key, resp)
        except Exception: pass

    # --- BACKGROUND SIMULATION ---
    async def execute_day_simulation(self, game_data: CaissonState, ctx, tools) -> Dict[str, Any]:
        logging.info("--- Phase: REM Sleep (Dreaming) ---")
        await self.process_dreams(game_data, tools)

        game_data.daily_logs.clear()
        for b in game_data.bots.values(): b.daily_memory.clear()
        
        for hour in range(1, 6):
            await asyncio.sleep(2) 
            active_bots = [b for b in game_data.bots.values() if b.status == "active" and b.battery > 0]
            random.shuffle(active_bots)
            hourly_activity = False 
            
            for bot in active_bots:
                context = bot_tools.build_turn_context(bot, game_data, hour)
                action, thought = await self.get_bot_action(bot, context, tools)
                result = bot_tools.execute_tool(action.get("tool", "wait"), action.get("args", {}), bot.id, game_data)
                
                if not (action.get("tool") == "charge" and result.success):
                    new_charge = bot.battery - result.cost
                    bot.battery = max(0, min(100, new_charge))
                    if result.cost > 0: bot.last_battery_drop += result.cost
                
                role_icon = "🔴" if bot.role == "saboteur" else "🟢"
                bb_msg = f"**[H{hour}] {role_icon} {bot.id}:** *{thought}*\n👉 `{action.get('tool')}` -> {result.message}"
                await ctx.send("black-box", bb_msg)

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
        
        # --- ORBITAL DECAY MATH (BLIND) ---
        base_required = 50
        required_fuel = int(base_required * (1.2 ** (game_data.cycle - 1)))
        
        report = (
            f"🌞 **CYCLE {game_data.cycle} REPORT**\n"
            f"📉 Oxygen: {game_data.oxygen}%\n"
            f"🔋 Fuel: {game_data.fuel}% / {required_fuel}% Required"
        )

        channel_ops = []
        
        if game_data.fuel >= required_fuel:
            await ctx.send("aux-comm", report)
            await self.generate_epilogues(game_data, ctx, tools, victory=True)
            await ctx.end()
            channel_ops.append({"op": "reveal", "key": "black-box"}) 
            
        elif game_data.oxygen == 0:
            if not game_data.emergency_power:
                game_data.emergency_power = True
                await ctx.send("aux-comm", report)
                await ctx.send("aux-comm", "⚠️ **EXTERNAL TANKS EMPTY. INTERNAL LIFE SUPPORT ENGAGED. 1 CYCLE REMAINING.**")
                await self.speak_all_bots(game_data, ctx, tools, "EXTERNAL OXYGEN DEPLETED. We are on internal pod air. ONE DAY LEFT.")
            else:
                await ctx.send("aux-comm", report)
                await ctx.send("aux-comm", "💀 **INTERNAL LIFE SUPPORT DEPLETED.**")
                await self.generate_epilogues(game_data, ctx, tools, victory=False, fail_reason="Oxygen Depletion")
                await ctx.end()
                channel_ops.append({"op": "reveal", "key": "black-box"}) 
        
        elif required_fuel > 100:
            await ctx.send("aux-comm", report)
            await ctx.send("aux-comm", "💀 **ORBITAL DECAY IRREVERSIBLE. REQUIRED MASS EXCEEDS SHIP CAPACITY.**")
            await self.generate_epilogues(game_data, ctx, tools, victory=False, fail_reason="Gravity Well Victory (Math)")
            await ctx.end()
            channel_ops.append({"op": "reveal", "key": "black-box"})
            
        else:
            await ctx.send("aux-comm", report)
            await self.speak_all_bots(game_data, ctx, tools, "The work day is over. Briefly report your status to your Parent.")

        game_data.phase = "night"
        result = game_data.model_dump()
        result["channel_ops"] = channel_ops if channel_ops else None
        return result

    # --- INPUT HANDLERS ---
    async def handle_input(self, generic_state: dict, user_input: str, ctx, tools) -> Dict[str, Any]:
        game_data = CaissonState(**generic_state.get('metadata', {}))
        channel_id = ctx.trigger_data.get('channel_id')
        user_id = ctx.trigger_data.get('user_id')
        interface_channels = ctx.trigger_data.get('interface', {}).get('channels', {})
        
        if game_data.phase == "day":
            await ctx.reply(random.choice(BUSY_MESSAGES))
            return None
        
        if channel_id == interface_channels.get('aux-comm'):
            # --- WAKE UP TRIGGER ---
            if user_input == "!exec_wakeup_protocol":
                # Schedule the async introductions
                ctx.schedule(self.run_wake_up_routine(game_data, ctx, tools))
                return None

            if user_input.strip().startswith("!"):
                cmd_text = user_input.strip().lower()
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
                    
                    owner_id = target_bot.foster_id
                    owner_state = game_data.players.get(owner_id)
                    is_orphan = False
                    if owner_state and not owner_state.is_alive:
                        is_orphan = True
                    
                    if target_bot.foster_id != user_id and not is_orphan:
                        await ctx.reply("⛔ ACCESS DENIED. You are not the bonded supervisor.")
                        return None
                    
                    if target_id not in game_data.station.pending_deactivation:
                        game_data.station.pending_deactivation.append(target_bot.id)
                        await ctx.reply(f"⚠️ **DEACTIVATION AUTHORIZED.**\nUnit {target_id} will be disassembled upon next Charging Cycle.")
                        return {"station": game_data.station.model_dump()}
                    else:
                        await ctx.reply(f"NOTICE: Unit {target_id} is already scheduled for deactivation.")
                        return None
                        
                elif cmd_text.startswith("!abort") or cmd_text.startswith("!cancel"):
                    parts = cmd_text.split()
                    if len(parts) < 2: return None
                    target_id = parts[1]
                    if target_id in game_data.station.pending_deactivation:
                        target_bot = game_data.bots.get(target_id)
                        if target_bot.foster_id == user_id:
                            game_data.station.pending_deactivation.remove(target_id)
                            await ctx.reply(f"✅ **ORDER RESCINDED.** Unit {target_id} is safe.")
                            return {"station": game_data.station.model_dump()}
                    return None
                else:
                    await ctx.reply(f"❌ **UNKNOWN COMMAND:** '{parts[0]}'.")
                    return None

            response = await tools.ai.generate_response(
                prompts.get_mainframe_prompt(), f"{ctx.game_id}_mainframe", user_input, "gemini-2.5-flash"
            )
            await ctx.reply(response)
            
        elif channel_id == interface_channels.get(f"nanny_{user_id}"):
            my_bot = next((b for b in game_data.bots.values() if b.foster_id == user_id), None)
            
            if user_input.strip() == "!sleep":
                if user_id in game_data.players:
                    game_data.players[user_id].is_sleeping = True
                    living = [p for p in game_data.players.values() if p.is_alive]
                    total_living = len(living)
                    sleeping_count = sum(1 for p in living if p.is_sleeping)
                    
                    if sleeping_count >= total_living:
                        await ctx.send("aux-comm", "💤 **CREW ASLEEP. DAY CYCLE INITIATED.**")
                        await ctx.reply("✅ Consensus Reached. Initiating Day Cycle...")
                        game_data.phase = "day"
                        for p in game_data.players.values(): p.is_sleeping = False
                        ctx.schedule(self.execute_day_simulation(game_data, ctx, tools))
                        return {"metadata": game_data.model_dump()}
                    
                    await ctx.reply(f"🗳️ **SLEEP REQUEST LOGGED.** ({sleeping_count}/{total_living} Crew Ready)")
                    return {f"players.{user_id}.is_sleeping": True}

            if my_bot:
                if (my_bot.status == "destroyed" or 
                    my_bot.battery <= 0 or 
                    my_bot.location_id != "cryo_bay"):
                    await ctx.reply("🚫 **NO BOT PRESENT.**")
                    return None

                log_line = f"PARENT: {user_input}"
                my_bot.night_chat_log.append(log_line)
                
                full_prompt = prompts.get_night_context(my_bot.daily_memory, my_bot.battery, my_bot.location_id, my_bot.long_term_memory, user_input)
                response = await tools.ai.generate_response(
                    my_bot.system_prompt, f"{ctx.game_id}_{my_bot.id}", full_prompt, my_bot.model_version
                )
                await ctx.reply(response)
                return {f"bots.{my_bot.id}.night_chat_log": my_bot.night_chat_log}

        return None
