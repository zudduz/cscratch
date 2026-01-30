from typing import Dict, Any, List, Optional, Tuple, Literal
import random
import asyncio
import logging
import json
import ast
import re
from pydantic import create_model, Field
from .models import Caisson, Drone, Player
from .board import GameConfig
from . import tools as drone_tools 
from . import ai_templates
from . import commands
from .ui_templates import FosterPresenter

class FosterProtocol:
    def __init__(self):
        default_state = Caisson()
        self.meta = {
            "name": "The Foster Protocol",
            "version": "2.49",
            **default_state.model_dump()
        }

    async def on_game_start(self, generic_state: dict) -> Dict[str, Any]:
        game_data = Caisson(**generic_state.get('metadata', {}))
        discord_players = generic_state.get('players', [])
        if not discord_players:
            return { "metadata": game_data.model_dump() }

        saboteur_index = random.randint(0, len(discord_players) - 1)
        
        # Logic calculates roles, Presenter defines the channel ops
        channel_ops = await FosterPresenter.list_channel_ops(discord_players, saboteur_index)
        
        # Initial Message buffer (Engine handles these differently than direct sends)
        messages = [{ "channel": "aux-comm", "content": "VENDETTA OS v9.0 ONLINE" }]

        for i, p_data in enumerate(discord_players):
            u_id = p_data['id']
            u_name = p_data['name']
            
            game_data.players[u_id] = Player(role="loyal", name=u_name)
            
            while True:
                drone_id = f"unit_{random.randint(0, 999):03d}"
                if drone_id not in game_data.drones:
                    break
            
            drone_role = "saboteur" if (i == saboteur_index) else "loyal"
            game_data.drones[drone_id] = Drone(
                id=drone_id, foster_id=u_id, role=drone_role, 
                model_version="gemini-2.5-flash"
            )

        return { "metadata": game_data.model_dump(), "channel_ops": channel_ops, "messages": messages }

    async def post_game_start(self, metadata: dict, ctx, tools) -> Dict[str, Any]:
        """Lifecycle hook called by the engine after all channels are created."""
        game_data = Caisson(**metadata)
        await self.run_wake_up_routine(game_data, ctx, tools)
        return {"metadata": game_data.model_dump()}

    # --- WAKE UP ROUTINE ---
    async def run_wake_up_routine(self, game_data, ctx, tools):
        logging.info("--- Waking up Drones for Introductions ---")
        tasks = []
        for drone in game_data.drones.values():
            tasks.append(self._generate_intro(drone, game_data, ctx, tools))
        if tasks: await asyncio.gather(*tasks)

    async def _generate_intro(self, drone, game_data, ctx, tools):
        try:
            sys_prompt, user_msg = ai_templates.compose_intro_turn(drone.id, game_data)
            
            resp = await tools.ai.generate_response(
                sys_prompt, f"{ctx.game_id}_drone_{drone.id}", user_msg, drone.model_version, game_id=ctx.game_id
            )
            await FosterPresenter.send_private_message(ctx, drone.foster_id, resp)
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
            sys_prompt, user_msg = ai_templates.compose_dream_turn(
                drone.long_term_memory, drone.daily_memory, drone.night_chat_log
            )
            
            new_memory = await tools.ai.generate_response(
                sys_prompt, f"dream_{drone.id}", user_msg, "gemini-2.5-flash"
            )
            drone.long_term_memory = new_memory.replace("\n", " ").strip()
            drone.night_chat_log = [] 
        except Exception as e:
            logging.error(f"Dream failed for {drone.id}: {e}")

    async def get_drone_action(self, drone, context_data, tools_api, game_id: str) -> tuple[Dict[str, Any], str]:
        try:
            context_data["schema"] = drone_tools.create_strict_action_model().model_json_schema()
            
            sys_prompt, user_msg = ai_templates.compose_tactical_turn(context_data)

            response_text = await tools_api.ai.generate_response(
                system_prompt=sys_prompt,
                conversation_id=f"tactical_{drone.id}",
                user_input=user_msg,
                model_version=drone.model_version,
                game_id=game_id,
                json_mode=True
            )

            try:
                clean_text = response_text.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_text)
                thought = data.get("thought_chain", "Drone acted without thinking")
                
                tool_call = {
                    "tool": data.get("tool", "wait"),
                    "args": data.get("args", {})
                }
                
                return tool_call, thought
                
            except json.JSONDecodeError:
                logging.error(f"Drone {drone.id} emitted invalid JSON in JSON Mode: {response_text}")
                return {"tool": "wait", "args": {}}, "System Error: Malformed JSON."

        except Exception as e:
            raw_text = locals().get('response_text', 'NO_RESPONSE_GENERATED')
            logging.error(f"Drone {drone.id} fatal error: {e}\nCaused by Input:\n{raw_text}")
            return {"tool": "wait", "args": {}}, f"Fatal Error: {str(e)}"

    async def speak_all_drones(self, game_data, ctx, tools, instruction):
        tasks = []
        for drone in game_data.drones.values():
            if not drone.can_talk:
                continue
            tasks.append(self._speak_single_drone(ctx, tools, drone, game_data, instruction))
        if tasks: await asyncio.gather(*tasks)

    async def _speak_single_drone(self, ctx, tools, drone, game_data, instruction):
        try:
            sys_prompt, user_msg = ai_templates.compose_speak_turn(drone.id, game_data, instruction)
            
            resp = await tools.ai.generate_response(
                sys_prompt, f"{ctx.game_id}_drone_{drone.id}", user_msg, drone.model_version, game_id=ctx.game_id
            )
            await FosterPresenter.send_private_message(ctx, drone.foster_id, resp)
        except Exception: pass

    async def _send_public_eulogy(self, ctx, tools, drone, game_data):
        try:
            sys_prompt, user_msg = ai_templates.compose_eulogy_turn(drone.id, game_data)
            
            resp = await tools.ai.generate_response(
                sys_prompt, f"{ctx.game_id}_drone_{drone.id}", user_msg, drone.model_version, game_id=ctx.game_id
            )
            await FosterPresenter.report_drone_eulogy(ctx, drone, resp)
        except Exception as e:
            logging.error(f"Eulogy failed for {drone.id}: {e}")

    async def generate_epilogues(self, game_data: Caisson, ctx, tools, victory: bool, fail_reason: str = ""):
        saboteur_drone = next((b for b in game_data.drones.values() if b.role == "saboteur"), None)
        foster_of_saboteur = game_data.players[saboteur_drone.foster_id]
        
        await FosterPresenter.announce_mission_end_log_reveal(ctx)
        await FosterPresenter.report_mission_summary(ctx, victory, fail_reason, saboteur_drone, foster_of_saboteur.name)
        
        tasks = []
        for drone in game_data.drones.values():
            if drone.status == "destroyed":
                 continue
            
            # Logic for status note handled in templates
            sys_prompt, user_msg = ai_templates.compose_epilogue_turn(drone.id, game_data, victory, fail_reason)
            tasks.append(self._generate_epilogue_response(ctx, tools, drone, sys_prompt, user_msg))
            
        if tasks:
            await asyncio.gather(*tasks)

    async def _generate_epilogue_response(self, ctx, tools, drone, sys, user):
        try:
             resp = await tools.ai.generate_response(sys, f"{ctx.game_id}_epilogue_{drone.id}", user, drone.model_version, game_id=ctx.game_id)
             await FosterPresenter.send_private_message(ctx, drone.foster_id, resp)
        except:
            pass

    async def run_single_drone_turn(self, drone, game_data, hour, tools, game_id):
        context_data = drone_tools.gather_turn_context_data(drone, game_data, hour)
        action, thought = await self.get_drone_action(drone, context_data, tools, game_id)
        result = drone_tools.execute_tool(action.get("tool", "wait"), action.get("args", {}), drone.id, game_data)
        
        return {
            "drone": drone,
            "action": action,
            "result": result,
            "thought": thought
        }

    async def execute_day_simulation(self, game_data: Caisson, ctx, tools) -> Dict[str, Any]:
        """
        Orchestrates the Day Phase using a pipeline pattern.
        """
        try:
            # 1. Dream Phase (Preparation)
            await self._run_dream_phase(game_data, tools)

            # 2. Work Shift Phase (The Loop)
            await self._run_work_shift(game_data, ctx, tools)

            # 3. Physics Phase (Calculations)
            physics_report = self._calculate_physics(game_data)

            # 4. Arbitration Phase (Rules)
            game_status, status_reason = self._evaluate_arbitration(game_data, physics_report)

            # 5. Transition Phase (Routing)
            result_payload = await self._handle_transition(game_data, game_status, status_reason, physics_report, ctx, tools)

            return result_payload
            
        except Exception as e:
            logging.error(f"execute_day_simulation died: {e}", exc_info=True)
            await FosterPresenter.send_system_error(ctx, str(e))
            return None

    # --- PIPELINE STAGES ---

    async def _run_dream_phase(self, game_data: Caisson, tools):
        """Processes logs from previous night into long term memory."""
        await self.process_dreams(game_data, tools)
        game_data.daily_logs.clear()
        for b in game_data.drones.values():
            b.daily_memory.clear()

    async def _run_work_shift(self, game_data: Caisson, ctx, tools):
        """Simulates the passage of 1 day's work."""
        for hour in range(1, GameConfig.HOURS_PER_SHIFT + 1):
            await asyncio.sleep(2) 
            active_drones = [b for b in game_data.drones.values() if b.status == "active"]
            random.shuffle(active_drones)
            hourly_activity = False 
            
            for drone in active_drones:
                await asyncio.sleep(0.3)
                try:
                    res = await self.run_single_drone_turn(drone, game_data, hour, tools, ctx.game_id)
                    drone_state = res['drone']
                    result = res['result']
                    
                    if result.event_type == "disassembly":
                        await self._send_public_eulogy(ctx, tools, drone_state, game_data)

                    # Report to Black Box
                    await FosterPresenter.report_blackbox_event(ctx, hour, drone_state, result, res['thought'])

                    # Memory Append
                    log_entry = f"[Hour {hour}] {result.message}"
                    drone_state.daily_memory.append(log_entry)
                    
                    # Witness Logic
                    if result.visibility in ["room", "global"]:
                        witnesses = [b for b in game_data.drones.values() if b.location_id == drone_state.location_id and b.id != drone_state.id]
                        for w in witnesses: 
                            w.daily_memory.append(f"[Hour {hour}] I saw {drone_state.id}: {result.message}")
                            
                    # Global Reporting
                    if result.visibility == "global":
                        public_msg = await FosterPresenter.report_public_event(ctx, hour, result.message)
                        game_data.daily_logs.append(public_msg)
                        hourly_activity = True
                        
                except Exception as e:
                    logging.error(f"Error running turn for drone {drone.id}: {e}", exc_info=True)

            if not hourly_activity:
                msg = await FosterPresenter.report_hourly_status_nominal(ctx, hour)
                game_data.daily_logs.append(msg)

    def _calculate_physics(self, game_data: Caisson) -> Dict[str, int]:
        """Calculates environmental decay and requirements."""
        living_crew = sum(1 for p in game_data.players.values() if p.alive)
        total_crew = max(1, len(game_data.players)) # Prevent div by zero
        
        drop_calc = int(GameConfig.OXYGEN_BASE_LOSS * (living_crew / total_crew))
        game_data.consume_oxygen(drop_calc)
        
        current_cycle = game_data.cycle
        req_today = int(GameConfig.FUEL_REQ_BASE * ((GameConfig.FUEL_REQ_GROWTH_PERCENT / 100) ** (current_cycle - 1)))
        req_tomorrow = int(GameConfig.FUEL_REQ_BASE * ((GameConfig.FUEL_REQ_GROWTH_PERCENT / 100) ** current_cycle))
        
        # Increment cycle for the NEXT day
        game_data.cycle += 1
        
        return {
            "oxygen_drop": drop_calc,
            "req_today": req_today,
            "req_tomorrow": req_tomorrow,
            "cycle_report_idx": current_cycle # Use the pre-incremented cycle for reporting "Report for Cycle X"
        }

    def _evaluate_arbitration(self, game_data: Caisson, physics: Dict[str, int]) -> Tuple[str, str]:
        """Determines if the game is Won, Lost, or Continuing."""
        if game_data.fuel >= physics["req_today"]:
            return "VICTORY", "Sufficient fuel achieved."
        elif physics["req_tomorrow"] > GameConfig.MAX_POSSIBLE_FUEL_REQ:
            return "FAILURE", "Required fuel exceeds ship capacity."
        return "CONTINUE", ""

    async def _handle_transition(self, game_data: Caisson, status: str, status_reason: str, physics: Dict[str, int], ctx, tools) -> Dict[str, Any]:
        """Handles the outcome of arbitration and returns the state patch."""
        
        # Report Status
        await FosterPresenter.report_cycle_status(
            ctx, 
            physics["cycle_report_idx"], 
            game_data.oxygen, 
            physics["oxygen_drop"], 
            game_data.fuel, 
            physics["req_today"]
        )

        channel_ops = []

        if status == "VICTORY":
            await FosterPresenter.report_victory(ctx)
            await self.generate_epilogues(game_data, ctx, tools, victory=True)
            await ctx.end()
            channel_ops.append({"op": "reveal", "key": "black-box"})

        elif status == "FAILURE":
            await FosterPresenter.report_failure_orbital_decay(ctx)
            await self.generate_epilogues(game_data, ctx, tools, victory=False, fail_reason=status_reason)
            await ctx.end()
            channel_ops.append({"op": "reveal", "key": "black-box"})

        else:
            # CONTINUE
            await FosterPresenter.report_cycle_continuation(ctx, physics["req_tomorrow"])
            
            # Auto-Continue Logic (If Oxygen is 0, crew is in stasis, we skip night chat)
            if game_data.is_ready_for_day:
                if game_data.oxygen <= 0:
                    await FosterPresenter.report_stasis_engaged(ctx)

                game_data.phase = "day"
                # Schedule recursive call for next day
                ctx.schedule(self.execute_day_simulation(game_data, ctx, tools))
            else:
                # Normal Night Phase
                await self.speak_all_drones(game_data, ctx, tools, ai_templates.format_drone_checkin())
                game_data.phase = "night"

        result = game_data.model_dump()
        result["channel_ops"] = channel_ops if channel_ops else None
        return result

    # --- INPUT HANDLERS ---

    async def handle_input(self, generic_state: dict, user_input: str, ctx, tools) -> Dict[str, Any]:
        game_data = Caisson(**generic_state.get('metadata', {}))
        channel_id = ctx.trigger_data.get('channel_id')
        user_id = ctx.trigger_data.get('user_id')
        interface_channels = ctx.trigger_data.get('interface', {}).get('channels', {})
        
        # 1. Block Input During Day
        if game_data.phase == "day":
            await FosterPresenter.reply_day_phase_active(ctx)
            return None
        
        # 2. Command Dispatcher
        if user_input.strip().startswith("!"):
            cmd_ctx = commands.CommandContext(self, game_data, ctx, tools, user_id, channel_id)
            return await commands.handle_command(user_input, cmd_ctx)

        # 3. Chat Routing
        if channel_id == interface_channels.get('aux-comm'):
            return await self._handle_mainframe_chat(user_input, ctx, tools)
            
        elif channel_id == interface_channels.get(f"nanny_{user_id}"):
            return await self._handle_drone_chat(user_input, ctx, tools, game_data, user_id)

        return None

    async def _handle_mainframe_chat(self, user_input, ctx, tools):
        sys_prompt, user_msg = ai_templates.compose_mainframe_turn(user_input)
        response = await tools.ai.generate_response(
            sys_prompt, f"{ctx.game_id}_mainframe", user_msg, "gemini-2.5-flash", game_id=ctx.game_id
        )
        await ctx.reply(response)
        return None

    async def _handle_drone_chat(self, user_input, ctx, tools, game_data, user_id):
        my_drone = next((b for b in game_data.drones.values() if b.foster_id == user_id), None)
        if my_drone:
            if not my_drone.can_talk:
                await FosterPresenter.reply_no_drone_present(ctx)
                return None

            log_line = ai_templates.format_parent_log_line(user_input)
            my_drone.night_chat_log.append(log_line)
            
            sys_prompt, user_msg = ai_templates.compose_nanny_chat_turn(
                my_drone.id,
                game_data,
                user_input
            )
            
            response = await tools.ai.generate_response(
                sys_prompt, f"{ctx.game_id}_{my_drone.id}", user_msg, my_drone.model_version, game_id=ctx.game_id
            )
            await ctx.reply(response)
            return {f"drones.{my_drone.id}.night_chat_log": my_drone.night_chat_log}
        return None