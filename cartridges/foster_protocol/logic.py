from typing import Dict, Any, List, Optional
import random
import asyncio
import logging
import json
import ast
import re
from .models import Caisson, Drone, Player
from .board import GameConfig
from . import tools as drone_tools 
from . import prompts

AVAILABLE_MODELS = ["gemini-2.5-flash"]

class FosterProtocol:
    def __init__(self):
        default_state = Caisson()
        self.meta = {
            "name": "The Foster Protocol",
            "version": "2.45",
            **default_state.model_dump()
        }

    async def on_game_start(self, generic_state: dict) -> Dict[str, Any]:
        game_data = Caisson(**generic_state.get('metadata', {}))
        discord_players = generic_state.get('players', [])
        if not discord_players: return { "metadata": game_data.model_dump() }

        game_data.initial_crew_size = len(discord_players)
        if game_data.initial_crew_size == 0: game_data.initial_crew_size = 1

        saboteur_index = random.randint(0, len(discord_players) - 1)
        channel_ops = []
        messages = []

        channel_ops.append({ "op": "create", "key": "aux-comm", "name": "aux-comm", "audience": "public" })
        channel_ops.append({ "op": "create", "key": "black-box", "name": "black-box-logs", "audience": "hidden", "init_msg": "FLIGHT RECORDER ACTIVE." })
        messages.append({ "channel": "aux-comm", "content": "VENDETTA OS v9.0 ONLINE." })

        base_text = prompts.get_base_prompt()

        for i, p_data in enumerate(discord_players):
            u_id = p_data['id']
            u_name = p_data['name']
            is_saboteur = (i == saboteur_index)
            role = "saboteur" if is_saboteur else "loyal"
            
            channel_key = f"nanny_{u_id}"
            channel_ops.append({ "op": "create", "key": channel_key, "name": f"nanny-port-{u_name}", "audience": "private", "user_id": u_id })
            
            game_data.players[u_id] = Player(role=role)
            
            while True:
                drone_id = f"unit_{random.randint(0, 999):03d}"
                if drone_id not in game_data.drones: break
            
            identity_block = prompts.get_drone_identity_block(drone_id, u_name, is_saboteur)
            
            # --- CACHING OPTIMIZATION ---
            system_prompt = base_text + "\n\n" + "--- IDENTITY OVERRIDE ---\n" + identity_block
            
            game_data.drones[drone_id] = Drone(
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
            prompt = prompts.get_intro_prompt()
            
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

    async def get_drone_action(self, drone, context_str, tools_api, game_id: str) -> tuple[Dict[str, Any], str]:
        try:
            enhanced_context = (
                context_str +
                "\n\n" + 
                prompts.get_thought_protocol()
            )

            response_text = await tools_api.ai.generate_response(
                system_prompt="You are a tactical drone. THINK BEFORE ACTING.",
                conversation_id=f"tactical_{drone.id}",
                user_input=enhanced_context,
                model_version=drone.model_version,
                game_id=game_id
            )

            # --- PARSING FIX: Handle Python List Output ---
            # The model sometimes returns a list of strings instead of a single string.
            if isinstance(response_text, list):
                response_text = "\n".join(str(item) for item in response_text)

            match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if match:
                json_text = match.group(0)
                pre_text = response_text[:match.start()].strip()
                post_text = response_text[match.end():].strip()
                thought_text = "Processing..."
                if pre_text:
                    thought_text = pre_text.replace("```json", "").replace("```", "").strip()
                elif post_text:
                    thought_text = post_text.replace("```json", "").replace("```", "").strip()
                
                return json.loads(json_text), thought_text

            logging.warning(f"Drone {drone.id} BRAIN FREEZE. Full Response:\n{response_text}")
            return {"tool": "wait", "args": {}}, "System Error: Neural Link Unstable (No JSON)."

        except Exception as e:
            # Capture the raw text to debug specific JSON syntax errors
            raw_text = locals().get('response_text', 'NO_RESPONSE_GENERATED')
            logging.error(f"Drone {drone.id} brain freeze: {e}\nCaused by Input:\n{raw_text}")
            return {"tool": "wait", "args": {}}, f"Brain Freeze: {str(e)}"

    async def speak_all_drones(self, game_data, ctx, tools, instruction):
        tasks = []
        for drone in game_data.drones.values():
            if not drone.can_talk:
                continue
            channel_key = f"nanny_{drone.foster_id}"
            tasks.append(self._speak_single_drone(ctx, tools, drone, instruction, channel_key))
        if tasks: await asyncio.gather(*tasks)

    async def _speak_single_drone(self, ctx, tools, drone, instruction, channel_key):
        try:
            full_prompt = prompts.get_speak_prompt(instruction, drone.battery)
            
            resp = await tools.ai.generate_response(
                drone.system_prompt, f"{ctx.game_id}_drone_{drone.id}", full_prompt, drone.model_version, game_id=ctx.game_id
            )
            await ctx.send(channel_key, resp)
        except Exception: pass

    async def _send_public_eulogy(self, ctx, tools, drone):
        try:
            prompt = prompts.get_eulogy_prompt()
            
            resp = await tools.ai.generate_response(
                drone.system_prompt, f"{ctx.game_id}_drone_{drone.id}", prompt, drone.model_version, game_id=ctx.game_id
            )
            display_name = drone.name if drone.name else drone.id
            role_reveal = f"**ANALYSIS:** DRONE WAS [{drone.role.upper()}]."
            msg = f"**DECOMMISSION LOG - {display_name}:**\n{role_reveal}\n*\"{resp}\"*"
            await ctx.send("aux-comm", msg)
        except Exception as e:
            logging.error(f"Eulogy failed for {drone.id}: {e}")

    async def generate_epilogues(self, game_data: Caisson, ctx, tools, victory: bool, fail_reason: str = ""):
        saboteur_id = next((pid for pid, p in game_data.players.items() if p.role == "saboteur"), None)
        saboteur_drone = next((b for b in game_data.drones.values() if b.foster_id == saboteur_id), None)
        drone_name = f"{saboteur_drone.name} ({saboteur_drone.id})" if (saboteur_drone and saboteur_drone.name) else (saboteur_drone.id if saboteur_drone else "UNKNOWN")
        
        await ctx.send("black-box", "MISSION ENDED. DECLASSIFYING LOGS...")
        
        if victory:
            final_report = f"SUBSPACE DRIVE ENGAGED\nMISSION: SUCCESS\nSECURITY AUDIT: Sabotage detected. Traitor: Drone {drone_name} (Bonded to <@{saboteur_id}>)."
        else:
            final_report = f"CRITICAL SYSTEM FAILURE\nREASON: {fail_reason}\nSECURITY ALERT: Traitor: Drone {drone_name} (Bonded to <@{saboteur_id}>)."
        await ctx.send("aux-comm", final_report)
        
        tasks = []
        for drone in game_data.drones.values():
            if drone.status == "destroyed":
                 continue
            
            channel_key = f"nanny_{drone.foster_id}"
            context_note = "STATUS: ONLINE."
            if drone.battery <= 0:
                 context_note = "STATUS: BATTERY DEAD. Final transmission."

            sys_prompt = prompts.get_epilogue_prompt(victory, drone.role, context_note)
            
            tasks.append(self._speak_single_drone(ctx, tools, drone, sys_prompt, channel_key))
        if tasks: await asyncio.gather(*tasks)

    async def run_single_drone_turn(self, drone, game_data, hour, tools, game_id):
        context_data = drone_tools.gather_turn_context_data(drone, game_data, hour)
        context_str = prompts.get_turn_context(context_data)
        
        action, thought = await self.get_drone_action(drone, context_str, tools, game_id)
        result = drone_tools.execute_tool(action.get("tool", "wait"), action.get("args", {}), drone.id, game_data)
        
        return {
            "drone": drone,
            "action": action,
            "result": result,
            "thought": thought
        }

    async def execute_day_simulation(self, game_data: Caisson, ctx, tools) -> Dict[str, Any]:
        
        try:
            logging.info("--- Phase: REM Sleep (Dreaming) ---")
            await self.process_dreams(game_data, tools)

            game_data.daily_logs.clear()
            for b in game_data.drones.values():
                b.daily_memory.clear()
            
            
            for hour in range(1, GameConfig.HOURS_PER_SHIFT + 1):
                await asyncio.sleep(2) 
                active_drones = [b for b in game_data.drones.values() if b.status == "active"]
                
                random.shuffle(active_drones)
                hourly_activity = False 
                
                for drone in active_drones:
                    await asyncio.sleep(0.3)
                    
                    try:
                        res = await self.run_single_drone_turn(drone, game_data, hour, tools, ctx.game_id)
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
                            public_msg = f"[HOUR {hour}] {result.message}"
                            
                            game_data.daily_logs.append(public_msg)
                            await ctx.send("aux-comm", public_msg) 
                            hourly_activity = True
                            
                    except Exception as e:
                        logging.error(f"--- [CRITICAL] Error running turn for drone {drone.id}: {e}", exc_info=True)

                if not hourly_activity:
                    game_data.daily_logs.append(f"[HOUR {hour}] Ship systems nominal.")
                    await ctx.send("aux-comm", f"[HOUR {hour}] Ship systems nominal.")

            living_crew = sum(1 for p in game_data.players.values() if p.alive)
            if game_data.initial_crew_size < 1: game_data.initial_crew_size = 1
            
            drop_calc = int(GameConfig.OXYGEN_BASE_LOSS * (living_crew / game_data.initial_crew_size))
            
            game_data.consume_oxygen(drop_calc)
            
            current_cycle = game_data.cycle
            
            # Requirement for the cycle that JUST finished
            req_today = int(GameConfig.FUEL_REQ_BASE * ((GameConfig.FUEL_REQ_GROWTH_PERCENT / 100) ** (current_cycle - 1)))
            
            # Requirement for the UPCOMING cycle (The Oberth penalty)
            req_tomorrow = int(GameConfig.FUEL_REQ_BASE * ((GameConfig.FUEL_REQ_GROWTH_PERCENT / 100) ** current_cycle))
            
            logging.info(f"--- [DEBUG] Cycle {current_cycle} | Fuel: {game_data.fuel}/{req_today} | O2: {game_data.oxygen} ---")

            # Increment Cycle
            game_data.cycle += 1
            
            report = (
                f"**CYCLE {current_cycle} REPORT**\n"
                f"Oxygen: {game_data.oxygen}% (-{drop_calc}%/day)\n"
                f"Fuel Status: {game_data.fuel}% / {req_today}% Required"
            )

            channel_ops = []
            
            if game_data.fuel >= req_today:
                await ctx.send("aux-comm", report + "\nSUCCESS SUFFICIENT FUEL FOR ESCAPE VELOCITY. INITIATING BURN...")
                await self.generate_epilogues(game_data, ctx, tools, victory=True)
                await ctx.end()
                channel_ops.append({"op": "reveal", "key": "black-box"}) 
                
            elif req_tomorrow > GameConfig.MAX_POSSIBLE_FUEL_REQ:
                await ctx.send("aux-comm", report)
                await ctx.send("aux-comm", "FATAL. ORBITAL DECAY IRREVERSIBLE. REQUIRED FUEL EXCEEDS SHIP CAPACITY.")
                await self.generate_epilogues(game_data, ctx, tools, victory=False, fail_reason="Required Fuel Exceeds Ships Capacity")
                await ctx.end()
                channel_ops.append({"op": "reveal", "key": "black-box"})
                
            else:
                report += f"\nBurn Window Missed. Atmospheric Drag detected.\n**Tomorrow's Fuel Target: {req_tomorrow}%**"
                await ctx.send("aux-comm", report)
                
                # --- AUTO-CONTINUE CHECK ---
                if game_data.is_ready_for_day:
                    # If O2 is gone, we announce it once here.
                    if game_data.oxygen <= 0:
                        logging.info("--- [DEBUG] O2 is 0. Triggering Stasis Message. ---")
                        await ctx.send("aux-comm", "**OXYGEN DEPLETED. STASIS ENGAGED.**\nThe Crew sleeps. The Drones must continue alone.")

                    # Ensure phase is set to day
                    game_data.phase = "day"
                    
                    # Schedule next day immediately
                    ctx.schedule(self.execute_day_simulation(game_data, ctx, tools))
                
                else:
                    # Normal Night Phase
                    await self.speak_all_drones(game_data, ctx, tools, "The work day is over. Briefly report your status to your Parent.")
                    game_data.phase = "night"

            result = game_data.model_dump()
            result["channel_ops"] = channel_ops if channel_ops else None
            return result
            
        except Exception as e:
            logging.error(f"--- [FATAL CRASH] execute_day_simulation died: {e}", exc_info=True)
            await ctx.send("aux-comm", f"SYSTEM ERROR. Simulation Halted: {str(e)}")
            return None

    async def handle_input(self, generic_state: dict, user_input: str, ctx, tools) -> Dict[str, Any]:
        game_data = Caisson(**generic_state.get('metadata', {}))
        channel_id = ctx.trigger_data.get('channel_id')
        user_id = ctx.trigger_data.get('user_id')
        interface_channels = ctx.trigger_data.get('interface', {}).get('channels', {})
        
        if game_data.phase == "day":
            await ctx.reply("Day Cycle in progress. You are sleeping now. Pretend to snore or something.")
            return None
        
        if channel_id == interface_channels.get('aux-comm'):
            if user_input.strip().startswith("!"):
                cmd_text = user_input.strip().lower()
                parts = cmd_text.split()
                if parts[0] == "!exec_wakeup_protocol":
                    ctx.schedule(self.run_wake_up_routine(game_data, ctx, tools))
                    return None

                if parts[0] == "!destroy":
                    if len(parts) < 2:
                        await ctx.reply("USAGE: !destroy <drone_id>")
                        return None
                    target_id = parts[1]
                    target_drone = game_data.drones.get(target_id)
                    if not target_drone:
                        await ctx.reply(f"Unit '{target_id}' not found.")
                        return None
                    
                    owner_id = target_drone.foster_id
                    owner_state = game_data.players.get(owner_id)
                    is_orphan = False
                    if owner_state and not owner_state.alive:
                        is_orphan = True
                    
                    if target_drone.foster_id != user_id and not is_orphan:
                        await ctx.reply("DENIED. You are not the bonded supervisor.")
                        return None
                    
                    if target_id not in game_data.station.pending_deactivation:
                        game_data.station.pending_deactivation.append(target_drone.id)
                        await ctx.reply(f"**DESTRUCTION AUTHORIZED.**\nDrone {target_id} will be destroyed upon next Charging Cycle.")
                        return {"station": game_data.station.model_dump()}
                    else:
                        await ctx.reply(f"Drone {target_id} is already scheduled for destruction.")
                        return None
                        
                elif parts[0] in ["!abort", "!cancel"]:
                    if len(parts) < 2: return None
                    target_id = parts[1]
                    if target_id in game_data.station.pending_deactivation:
                        target_drone = game_data.drones.get(target_id)
                        if target_drone.foster_id == user_id:
                            game_data.station.pending_deactivation.remove(target_id)
                            await ctx.reply(f"**ORDER RESCINDED.** Drone {target_id} is safe.")
                            return {"station": game_data.station.model_dump()}
                    return None
                else:
                    await ctx.reply(f"**UNKNOWN COMMAND:** '{parts[0]}'.")
                    return None

            response = await tools.ai.generate_response(
                prompts.get_mainframe_prompt(), f"{ctx.game_id}_mainframe", user_input, "gemini-2.5-flash", game_id=ctx.game_id
            )
            await ctx.reply(response)
            
        elif channel_id == interface_channels.get(f"nanny_{user_id}"):
            my_drone = next((b for b in game_data.drones.values() if b.foster_id == user_id), None)
            
            if user_input.strip().startswith("!"):
                cmd_text = user_input.strip().lower()

                if cmd_text.startswith("!name"):
                    if not my_drone: return None
                    parts = user_input.strip().split(maxsplit=1)
                    if len(parts) < 2:
                        await ctx.reply("USAGE: !name <new_name>")
                        return None
                    new_name = parts[1][:20]
                    my_drone.name = new_name
                    
                    base_text = prompts.get_base_prompt()
                    identity_block = prompts.get_drone_identity_block(my_drone.id, game_data.players[user_id].role, my_drone.role == "saboteur")
                    
                    # --- CACHING OPTIMIZATION ---
                    identity_patch = "\n\n" + prompts.get_identity_update_prompt(new_name)
                    final_identity = identity_block + identity_patch
                    
                    my_drone.system_prompt = base_text + "\n\n" + "--- IDENTITY OVERRIDE ---\n" + final_identity
                    
                    await ctx.reply(f"Identity Updated. Hello, **{new_name}**.")
                    return {f"drones.{my_drone.id}.name": new_name, f"drones.{my_drone.id}.system_prompt": my_drone.system_prompt}
                
                elif cmd_text == "!sleep":
                    if user_id in game_data.players:
                        game_data.players[user_id].requested_sleep = True
                        
                        if game_data.is_ready_for_day:
                            logging.info(f"--- [DEBUG] Consensus Reached via !sleep. User {user_id} triggered Day Cycle. ---")
                            await ctx.send("aux-comm", "**CREW ASLEEP. DAY CYCLE INITIATED.**")
                            await ctx.reply("Consensus Reached. Initiating Day Cycle...")
                            game_data.phase = "day"
                            for p in game_data.players.values():
                                p.requested_sleep = False
                            ctx.schedule(self.execute_day_simulation(game_data, ctx, tools))
                            return {"metadata": game_data.model_dump()}
                        
                        await ctx.reply(f"**SLEEP REQUEST LOGGED.**")
                        return {f"players.{user_id}.requested_sleep": True}
                
                else:
                    # Rejects any other !command instead of sending it as a message
                    await ctx.reply(f"Unknown Nanny Command: '{cmd_text}'.\nAvailable: !name <name>, !sleep")
                    return None

            if my_drone:
                if not my_drone.can_talk:
                    await ctx.reply("**NO DRONE PRESENT.**")
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