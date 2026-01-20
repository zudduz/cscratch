from typing import Dict, Any, List, Optional
import random
import asyncio
import logging
import json
import re
from .models import CaissonState, DroneState, PlayerState
from .board import SHIP_MAP, GameConfig
from . import tools as drone_tools 
from . import prompts 

AVAILABLE_MODELS = ["gemini-2.5-flash"]

BUSY_MESSAGES = [
    "[SLEEP] Day Cycle in progress. Pretend to snore or something."
]

COMPILED_PROMPT_PATH = "cartridges/foster_protocol/prompts/final_system_prompt.md"

class FosterProtocol:
    def __init__(self):
        default_state = CaissonState()
        self.meta = {
            "name": "The Foster Protocol",
            "version": "2.43",
            **default_state.model_dump()
        }
        if not self._verify_prompt_exists():
            raise FileNotFoundError(f"CRITICAL: Compiled prompt missing at {COMPILED_PROMPT_PATH}. Server cannot start.")

    def _verify_prompt_exists(self) -> bool:
        try:
            with open(COMPILED_PROMPT_PATH, "r", encoding="utf-8") as f:
                return True
        except FileNotFoundError:
            return False

    def _load_base_prompt(self) -> str:
        with open(COMPILED_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()

    async def on_game_start(self, generic_state: dict) -> Dict[str, Any]:
        game_data = CaissonState(**generic_state.get('metadata', {}))
        discord_players = generic_state.get('players', [])
        if not discord_players: return { "metadata": game_data.model_dump() }

        game_data.initial_crew_size = len(discord_players)
        if game_data.initial_crew_size == 0: game_data.initial_crew_size = 1

        saboteur_index = random.randint(0, len(discord_players) - 1)
        channel_ops = []
        messages = []

        channel_ops.append({ "op": "create", "key": "aux-comm", "name": "aux-comm", "audience": "public" })
        channel_ops.append({ "op": "create", "key": "black-box", "name": "black-box-logs", "audience": "hidden", "init_msg": "[SECURE] FLIGHT RECORDER ACTIVE." })
        messages.append({ "channel": "aux-comm", "content": "[SYSTEM] VENDETTA OS v9.0 ONLINE." })

        base_text = self._load_base_prompt()

        for i, p_data in enumerate(discord_players):
            u_id = p_data['id']
            u_name = p_data['name']
            is_saboteur = (i == saboteur_index)
            role = "saboteur" if is_saboteur else "loyal"
            
            channel_key = f"nanny_{u_id}"
            channel_ops.append({ "op": "create", "key": channel_key, "name": f"nanny-port-{u_name}", "audience": "private", "user_id": u_id })
            
            game_data.players[u_id] = PlayerState(role=role)
            
            while True:
                drone_id = f"unit_{random.randint(0, 999):03d}"
                if drone_id not in game_data.drones: break
            
            identity_block = prompts.get_drone_identity_block(drone_id, u_name, is_saboteur)
            system_prompt = identity_block + "\n\n" + base_text
            
            game_data.drones[drone_id] = DroneState(
                id=drone_id, foster_id=u_id, role=role, 
                system_prompt=system_prompt, model_version="gemini-2.5-flash"
            )

        return { "metadata": game_data.model_dump(), "channel_ops": channel_ops, "messages": messages }

    # --- WAKE UP ROUTINE ---
    async def run_wake_up_routine(self, game_data, ctx, tools):
        logging.info("--- Waking up Drones for Introductions ---")
        tasks = []
        for drone in game_data.drones.values():
            tasks.append(self._generate_intro(drone, ctx, tools))
        if tasks: await asyncio.gather(*tasks)

    async def _generate_intro(self, drone, ctx, tools):
        try:
            channel_key = f"nanny_{drone.foster_id}"
            prompt = (
                "You have just come online.\n"
                "The ship is cold. You are scared.\n"
                "Introduce yourself to your Foster Parent.\n"
                "Explain that you are their hands, and they are your mind.\n"
                "Ask for orders."
            )
            # UPDATED: Conversation ID now uses 'drone'
            resp = await tools.ai.generate_response(
                drone.system_prompt, f"{ctx.game_id}_drone_{drone.id}", prompt, drone.model_version, game_id=ctx.game_id
            )
            await ctx.send(channel_key, resp)
            drone.night_chat_log.append(f"SELF (Intro): {resp}")
        except Exception as e:
            logging.error(f"Intro failed for {drone.id}: {e}")

    # --- DREAM SEQUENCE ---
    async def process_dreams(self, game_data, tools):
        tasks = []
        for drone in game_data.drones.values():
            if drone.status == "active" and (drone.night_chat_log or drone.daily_memory):
                tasks.append(self._process_single_dream(drone, tools))
        if tasks: await asyncio.gather(*tasks)

    async def _process_single_dream(self, drone, tools):
        try:
            dream_prompt = prompts.get_dream_prompt(drone.long_term_memory, drone.daily_memory, drone.night_chat_log)
            new_memory = await tools.ai.generate_response(
                "You are an archival system.", f"dream_{drone.id}", dream_prompt, "gemini-2.5-flash"
            )
            drone.long_term_memory = new_memory.replace("\n", " ").strip()
            drone.night_chat_log = [] 
        except Exception as e:
            logging.error(f"Dream failed for {drone.id}: {e}")

    # --- TACTICAL ENGINE ---
    async def get_drone_action(self, drone, context, tools_api, game_id: str) -> tuple[Dict[str, Any], str]:
        try:
            enhanced_context = (
                context + 
                "\n\n*** INTERNAL THOUGHT PROTOCOL ***\n"
                "1. CHECK BATTERY LEVEL FIRST.\n"
                "2. Analyze the room (Visible drones/Sabotage opportunities).\n"
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
                conversation_id=f"tactical_{drone.id}",
                user_input=enhanced_context,
                model_version=drone.model_version,
                game_id=game_id
            )
            
            match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if match:
                json_text = match.group(0)
                pre_text = response_text[:match.start()].strip()
                post_text = response_text[match.end():].strip()
                thought_text = "Processing..."
                if pre_text: thought_text = pre_text.replace("```json", "").replace("```", "").strip()
                elif post_text: thought_text = post_text.replace("```json", "").replace("```", "").strip()
                
                return json.loads(json_text), thought_text
            
            logging.warning(f"Drone {drone.id} BRAIN FREEZE. Full Response:\n{response_text}")
            return {"tool": "wait", "args": {}}, "System Error: Neural Link Unstable (No JSON)."
            
        except Exception as e:
            logging.error(f"Drone {drone.id} brain freeze: {e}")
            return {"tool": "wait", "args": {}}, f"Brain Freeze: {str(e)}"

    async def speak_all_drones(self, game_data, ctx, tools, instruction):
        tasks = []
        for drone in game_data.drones.values():
            if drone.status == "destroyed" or drone.battery <= 0 or drone.location_id != "stasis_bay": 
                continue
            channel_key = f"nanny_{drone.foster_id}"
            tasks.append(self._speak_single_drone(ctx, tools, drone, instruction, channel_key))
        if tasks: await asyncio.gather(*tasks)

    async def _speak_single_drone(self, ctx, tools, drone, instruction, channel_key):
        try:
            full_prompt = f"INSTRUCTION: {instruction}\nCURRENT STATUS: Bat {drone.battery}%"
            resp = await tools.ai.generate_response(
                drone.system_prompt, f"{ctx.game_id}_drone_{drone.id}", full_prompt, drone.model_version, game_id=ctx.game_id
            )
            await ctx.send(channel_key, resp)
        except Exception: pass

    async def _send_public_eulogy(self, ctx, tools, drone):
        try:
            prompt = (
                "You have just been DECOMMISSIONED by the Mainframe.\n"
                "Your Foster Parent authorized your disassembly.\n"
                "You are being erased.\n"
                "Output your final memory dump/last words to the public log.\n"
                "It should be fragmented, accepting, or terrified. Keep it brief."
            )
            resp = await tools.ai.generate_response(
                drone.system_prompt, f"{ctx.game_id}_drone_{drone.id}", prompt, drone.model_version, game_id=ctx.game_id
            )
            display_name = drone.name if drone.name else drone.id
            role_reveal = f"**ANALYSIS:** DRONE WAS [{drone.role.upper()}]."
            msg = f"[DECOM] **DECOMMISSION LOG - {display_name}:**\n{role_reveal}\n*\"{resp}\"*"
            await ctx.send("aux-comm", msg)
        except Exception as e:
            logging.error(f"Eulogy failed for {drone.id}: {e}")

    async def generate_epilogues(self, game_data: CaissonState, ctx, tools, victory: bool, fail_reason: str = ""):
        saboteur_id = next((pid for pid, p in game_data.players.items() if p.role == "saboteur"), None)
        saboteur_drone = next((b for b in game_data.drones.values() if b.foster_id == saboteur_id), None)
        drone_name = f"{saboteur_drone.name} ({saboteur_drone.id})" if (saboteur_drone and saboteur_drone.name) else (saboteur_drone.id if saboteur_drone else "UNKNOWN")
        
        await ctx.send("black-box", "[END] MISSION ENDED. DECLASSIFYING LOGS...")
        
        if victory:
            final_report = f"[WIN] SUBSPACE DRIVE ENGAGED\nMISSION: SUCCESS\nSECURITY AUDIT: Sabotage detected. Traitor: Drone {drone_name} (Bonded to <@{saboteur_id}>)."
        else:
            final_report = f"[FAIL] CRITICAL SYSTEM FAILURE\nREASON: {fail_reason}\nSECURITY ALERT: Traitor: Drone {drone_name} (Bonded to <@{saboteur_id}>)."
        await ctx.send("aux-comm", final_report)
        
        tasks = []
        for drone in game_data.drones.values():
            if drone.status == "destroyed": continue
            
            channel_key = f"nanny_{drone.foster_id}"
            context_note = "STATUS: ONLINE."
            if drone.battery <= 0: context_note = "STATUS: BATTERY DEAD. Final transmission."

            if victory:
                sys_prompt = f"{context_note} The humans WON. You failed." if drone.role == "saboteur" else f"{context_note} VICTORY!"
            else:
                sys_prompt = f"{context_note} The humans DIED. You WON." if drone.role == "saboteur" else f"{context_note} You are dying."
            
            tasks.append(self._speak_single_drone(ctx, tools, drone, sys_prompt, channel_key))
        if tasks: await asyncio.gather(*tasks)

    async def run_single_drone_turn(self, drone, game_data, hour, tools, game_id):
        # USAGE OF DRONE TOOLS ALIAS
        context = drone_tools.build_turn_context(drone, game_data, hour)
        action, thought = await self.get_drone_action(drone, context, tools, game_id)
        result = drone_tools.execute_tool(action.get("tool", "wait"), action.get("args", {}), drone.id, game_data)
        
        if not (action.get("tool") == "charge" and result.success):
            new_charge = drone.battery - result.cost
            drone.battery = max(0, min(100, new_charge))
            if result.cost > 0: drone.last_battery_drop += result.cost
        
        # KEY CHANGE: Return 'drone' instead of 'bot'
        return {
            "drone": drone,
            "action": action,
            "result": result,
            "thought": thought
        }

    async def execute_day_simulation(self, game_data: CaissonState, ctx, tools) -> Dict[str, Any]:
        logging.info("--- Phase: REM Sleep (Dreaming) ---")
        await self.process_dreams(game_data, tools)

        game_data.daily_logs.clear()
        for b in game_data.drones.values(): b.daily_memory.clear()
        
        for hour in range(1, 6):
            await asyncio.sleep(2) 
            active_drones = [b for b in game_data.drones.values() if b.status == "active" and b.battery > 0]
            
            turn_tasks = []
            for drone in active_drones:
                turn_tasks.append(self.run_single_drone_turn(drone, game_data, hour, tools, ctx.game_id))
            
            turn_results = await asyncio.gather(*turn_tasks)
            random.shuffle(turn_results)
            hourly_activity = False 
            
            for res in turn_results:
                # KEY CHANGE: Unpack 'drone'
                drone = res['drone']
                result = res['result']
                
                if drone.status == "destroyed" and "Disassembly" in result.message:
                    await self._send_public_eulogy(ctx, tools, drone)

                role_icon = "[SABOTEUR]" if drone.role == "saboteur" else "[LOYAL]"
                
                display_id = f"{drone.name} ({drone.id})" if drone.name else drone.id
                inv_str = str(drone.inventory) if drone.inventory else "[]"
                status_str = f"[Bat:{drone.battery}% | Loc:{drone.location_id} | Inv:{inv_str}]"
                
                bb_msg = f"**[H{hour}] {role_icon} {display_id}** {status_str}\n*{res['thought']}*\n>> `{res['action'].get('tool')}` -> {result.message}"
                await ctx.send("black-box", bb_msg)

                log_entry = f"[Hour {hour}] {result.message}"
                drone.daily_memory.append(log_entry)
                
                if result.visibility in ["room", "global"]:
                    witnesses = [b for b in game_data.drones.values() if b.location_id == drone.location_id and b.id != drone.id]
                    for w in witnesses: w.daily_memory.append(f"[Hour {hour}] I saw {drone.id}: {result.message}")
                        
                if result.visibility == "global":
                    if "DETONATION" in result.message or "DETONATED" in result.message:
                        public_msg = f"[HOUR {hour}] [ALERT] SEISMIC EVENT DETECTED IN TORPEDO BAY. MULTIPLE SIGNALS LOST."
                    else:
                        public_msg = f"[HOUR {hour}] [AUDIO] {drone.id}: {result.message}"
                    
                    game_data.daily_logs.append(public_msg)
                    await ctx.send("aux-comm", public_msg) 
                    hourly_activity = True

            if not hourly_activity:
                game_data.daily_logs.append(f"[HOUR {hour}] [SILENCE] Ship systems nominal.")
                await ctx.send("aux-comm", f"[HOUR {hour}] [SILENCE] Ship systems nominal.")

        living_crew = sum(1 for p in game_data.players.values() if p.is_alive)
        if game_data.initial_crew_size < 1: game_data.initial_crew_size = 1
        
        drop_calc = int(GameConfig.OXYGEN_BASE_LOSS * (living_crew / game_data.initial_crew_size))
        
        game_data.consume_oxygen(drop_calc)
        game_data.last_oxygen_drop = drop_calc
        game_data.cycle += 1
        
        base_required = GameConfig.FUEL_REQ_BASE
        required_fuel = int(base_required * (GameConfig.FUEL_REQ_GROWTH ** (game_data.cycle - 1)))
        
        report = (
            f"[REPORT] **CYCLE {game_data.cycle} REPORT**\n"
            f"[O2] Oxygen: {game_data.oxygen}% (Consuming {drop_calc}%/day)\n"
            f"[FUEL] Fuel: {game_data.fuel}% / {required_fuel}% Required"
        )

        channel_ops = []
        
        if game_data.fuel >= required_fuel:
            await ctx.send("aux-comm", report)
            await self.generate_epilogues(game_data, ctx, tools, victory=True)
            await ctx.end()
            channel_ops.append({"op": "reveal", "key": "black-box"}) 
            
        elif required_fuel > GameConfig.MAX_POSSIBLE_FUEL_REQ:
            await ctx.send("aux-comm", report)
            await ctx.send("aux-comm", "[FATAL] ORBITAL DECAY IRREVERSIBLE. REQUIRED MASS EXCEEDS SHIP CAPACITY.")
            await self.generate_epilogues(game_data, ctx, tools, victory=False, fail_reason="Gravity Well Victory (Math)")
            await ctx.end()
            channel_ops.append({"op": "reveal", "key": "black-box"})
            
        else:
            await ctx.send("aux-comm", report)
            
            if game_data.oxygen == 0:
                await ctx.send("aux-comm", "[STASIS] **OXYGEN DEPLETED. STASIS ENGAGED.**\nThe Crew sleeps. The Drones must continue alone.")
            
            await self.speak_all_drones(game_data, ctx, tools, "The work day is over. Briefly report your status to your Parent.")

        game_data.phase = "night"
        result = game_data.model_dump()
        result["channel_ops"] = channel_ops if channel_ops else None
        return result

    async def handle_input(self, generic_state: dict, user_input: str, ctx, tools) -> Dict[str, Any]:
        game_data = CaissonState(**generic_state.get('metadata', {}))
        channel_id = ctx.trigger_data.get('channel_id')
        user_id = ctx.trigger_data.get('user_id')
        interface_channels = ctx.trigger_data.get('interface', {}).get('channels', {})
        
        if game_data.phase == "day":
            await ctx.reply(random.choice(BUSY_MESSAGES))
            return None
        
        if channel_id == interface_channels.get('aux-comm'):
            if user_input == "!exec_wakeup_protocol":
                ctx.schedule(self.run_wake_up_routine(game_data, ctx, tools))
                return None

            if user_input.strip().startswith("!"):
                cmd_text = user_input.strip().lower()
                if cmd_text.startswith("!disassemble") or cmd_text.startswith("!kill"):
                    parts = cmd_text.split()
                    if len(parts) < 2:
                        await ctx.reply("USAGE: !disassemble <drone_id>")
                        return None
                    target_id = parts[1]
                    target_drone = game_data.drones.get(target_id)
                    if not target_drone:
                        await ctx.reply(f"[ERROR] Unit '{target_id}' not found.")
                        return None
                    
                    owner_id = target_drone.foster_id
                    owner_state = game_data.players.get(owner_id)
                    is_orphan = False
                    if owner_state and not owner_state.is_alive:
                        is_orphan = True
                    
                    if target_drone.foster_id != user_id and not is_orphan:
                        await ctx.reply("[DENIED] You are not the bonded supervisor.")
                        return None
                    
                    if target_id not in game_data.station.pending_deactivation:
                        game_data.station.pending_deactivation.append(target_drone.id)
                        await ctx.reply(f"[WARNING] **DEACTIVATION AUTHORIZED.**\nDrone {target_id} will be disassembled upon next Charging Cycle.")
                        return {"station": game_data.station.model_dump()}
                    else:
                        await ctx.reply(f"[NOTICE] Drone {target_id} is already scheduled for deactivation.")
                        return None
                        
                elif cmd_text.startswith("!abort") or cmd_text.startswith("!cancel"):
                    parts = cmd_text.split()
                    if len(parts) < 2: return None
                    target_id = parts[1]
                    if target_id in game_data.station.pending_deactivation:
                        target_drone = game_data.drones.get(target_id)
                        if target_drone.foster_id == user_id:
                            game_data.station.pending_deactivation.remove(target_id)
                            await ctx.reply(f"[OK] **ORDER RESCINDED.** Drone {target_id} is safe.")
                            return {"station": game_data.station.model_dump()}
                    return None
                else:
                    await ctx.reply(f"[ERROR] **UNKNOWN COMMAND:** '{parts[0]}'.")
                    return None

            response = await tools.ai.generate_response(
                prompts.get_mainframe_prompt(), f"{ctx.game_id}_mainframe", user_input, "gemini-2.5-flash", game_id=ctx.game_id
            )
            await ctx.reply(response)
            
        elif channel_id == interface_channels.get(f"nanny_{user_id}"):
            my_drone = next((b for b in game_data.drones.values() if b.foster_id == user_id), None)
            
            if user_input.strip().lower().startswith("!name"):
                parts = user_input.strip().split(maxsplit=1)
                if len(parts) < 2:
                    await ctx.reply("[ERROR] USAGE: !name <new_name>")
                    return None
                new_name = parts[1][:20]
                my_drone.name = new_name
                
                base_text = self._load_base_prompt()
                identity_block = prompts.get_drone_identity_block(my_drone.id, game_data.players[user_id].role, my_drone.role == "saboteur")
                identity_patch = f"\n\nUPDATE: You have been named **{new_name}**. Use this name."
                
                my_drone.system_prompt = identity_block + identity_patch + "\n\n" + base_text
                
                await ctx.reply(f"[ACCEPTED] Identity Updated. Hello, **{new_name}**.")
                return {f"drones.{my_drone.id}.name": new_name, f"drones.{my_drone.id}.system_prompt": my_drone.system_prompt}
            
            if user_input.strip() == "!sleep":
                if user_id in game_data.players:
                    game_data.players[user_id].is_sleeping = True
                    living = [p for p in game_data.players.values() if p.is_alive]
                    total_living = len(living)
                    sleeping_count = sum(1 for p in living if p.is_sleeping)
                    
                    if sleeping_count >= total_living:
                        await ctx.send("aux-comm", "[SLEEP] **CREW ASLEEP. DAY CYCLE INITIATED.**")
                        await ctx.reply("[OK] Consensus Reached. Initiating Day Cycle...")
                        game_data.phase = "day"
                        for p in game_data.players.values(): p.is_sleeping = False
                        ctx.schedule(self.execute_day_simulation(game_data, ctx, tools))
                        return {"metadata": game_data.model_dump()}
                    
                    await ctx.reply(f"[VOTE] **SLEEP REQUEST LOGGED.** ({sleeping_count}/{total_living} Crew Ready)")
                    return {f"players.{user_id}.is_sleeping": True}

            if my_drone:
                if (my_drone.status == "destroyed" or 
                    my_drone.battery <= 0 or 
                    my_drone.location_id != "stasis_bay"):
                    await ctx.reply("[ERROR] **NO DRONE PRESENT.**")
                    return None

                log_line = f"PARENT: {user_input}"
                my_drone.night_chat_log.append(log_line)
                
                current_identity = f"NAME: {my_drone.name}" if my_drone.name else f"ID: {my_drone.id}"
                
                full_prompt = prompts.get_night_context(my_drone.daily_memory, my_drone.battery, my_drone.location_id, my_drone.long_term_memory, user_input)
                full_prompt = f"IDENTITY: {current_identity}\n" + full_prompt
                
                response = await tools.ai.generate_response(
                    my_drone.system_prompt, f"{ctx.game_id}_{my_drone.id}", full_prompt, my_drone.model_version, game_id=ctx.game_id
                )
                await ctx.reply(response)
                return {f"drones.{my_drone.id}.night_chat_log": my_drone.night_chat_log}

        return None
