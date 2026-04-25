from typing import Dict, Any, List, Optional, Tuple, Literal
import random
import asyncio
import logging
import json
import re
from .models import Caisson, Drone, Player
from .board import GameConfig, GameEndState
from . import tools as drone_tools 
from . import ai_templates
from . import commands
from .ui_templates import FosterPresenter

class FosterProtocol:
    def __init__(self):
        default_state = Caisson()
        self.meta = {
            "name": "The Foster Protocol",
            "version": default_state.version,
            **default_state.model_dump()
        }
        
        # Explicit Task Dispatcher Registry
        self._task_handlers = {
            "dream_phase": self._handle_dream_phase,
            "tick_hour": self._handle_tick_hour,
            "dusk_phase": self._handle_dusk_phase,
            "physics_arbitration": self._handle_physics_arbitration
        }

    @property
    def MAX_PLAYERS(self):
        return GameConfig.MAX_PLAYERS

    def calculate_start_cost(self, player_count: int) -> int:
        return max(4, player_count)

    async def on_game_start(self, generic_state: dict) -> Dict[str, Any]:
        game_data = Caisson(**generic_state.get('metadata', {}))
        discord_players = generic_state.get('players', [])
        guild_id = generic_state.get('interface', {}).get('guild_id')
        
        if not discord_players:
            return { "metadata": game_data.model_dump() }

        saboteur_index = random.randint(0, len(discord_players) - 1)
        
        # Logic calculates roles, Presenter defines the channel ops
        channel_ops = await FosterPresenter.list_channel_ops(discord_players, saboteur_index, guild_id)
        
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

            messages.append({
                "channel": f"nanny_{u_id}", 
                "content": f"New client detected\nID: {drone_id}"
            })

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
            tasks.append(asyncio.create_task(self._generate_intro(drone, game_data, ctx, tools)))
            await asyncio.sleep(GameConfig.AI_PARALLEL_DELAY)
        if tasks: await asyncio.gather(*tasks)

    async def _generate_intro(self, drone, game_data, ctx, tools):
        try:
            sys_prompt, user_msg = ai_templates.compose_intro_turn(drone.id, game_data)
            
            resp = await tools.ai.generate_response(
                sys_prompt, f"{ctx.game_id}_drone_{drone.id}", user_msg, drone.model_version, game_id=ctx.game_id
            )
            await FosterPresenter.send_private_message(ctx, drone.foster_id, resp)
            drone.night_chat_log.append(ai_templates.format_drone_log_line(resp))
        except Exception as e:
            logging.error(f"Intro failed for {drone.id}: {e}")

    # --- DREAM SEQUENCE ---
    async def _process_single_dream(self, drone: Drone, game_data: Caisson, tools):
        try:
            sys_prompt, user_msg = ai_templates.compose_dream_turn(drone, game_data)
            
            new_memory = await tools.ai.generate_response(
                sys_prompt, f"dream_{drone.id}", user_msg, drone.model_version
            )
            drone.long_term_memory = new_memory.replace("\n", " ").strip()
            drone.night_chat_log.clear()
            drone.daily_memory.clear()
            drone.daily_event_log.clear()
        except Exception as e:
            logging.error(f"Dream failed for {drone.id}: {e}")

    async def get_drone_action(self, drone, game_data: Caisson, tools_api, game_id: str, hour: int) -> tuple[Dict[str, Any], str]:
        try:
            # INJECT SCHEMA (for guidance only)
            schema = drone_tools.create_strict_action_model().model_json_schema()
            sys_prompt, user_msg = ai_templates.compose_tactical_turn(drone, game_data, hour)

            response_text = await tools_api.ai.generate_response(
                system_prompt=sys_prompt,
                conversation_id=f"tactical_{drone.id}",
                user_input=user_msg,
                model_version=drone.model_version,
                game_id=game_id,
                response_schema=schema
            )

            # The model sometimes returns a list of strings instead of a single string.
            if isinstance(response_text, list):
                response_text = "\n".join(str(item) for item in response_text)

            if not response_text:
                logging.error(f"Drone {drone.id} returned empty string.")
                return {"tool": "invalid"}, "Drone provided empty response."

            # Find the first valid JSON block { ... } matching curly braces
            match = re.search(r"(\{.*\})", response_text, re.DOTALL)
            
            if match:
                clean_json = match.group(1)
                try:
                    data = json.loads(clean_json)
                    thought = response_text
                    
                    tool_call = {
                        "tool": data.get("tool", "invalid"),
                        "args": data
                    }
                    return tool_call, thought
                    
                except json.JSONDecodeError:
                    logging.error(f"Drone {drone.id} emitted invalid JSON: {clean_json}")
                    return {"tool": "invalid"}, "System Error: Malformed JSON."
            else:
                logging.error(f"Drone {drone.id} output no JSON block: {response_text}")
                return {"tool": "invalid"}, "System Error: No Action Data."

        except Exception as e:
            raw_text = locals().get('response_text', 'NO_RESPONSE_GENERATED')
            logging.error(f"Drone {drone.id} fatal error: {e}\nCaused by Input:\n{raw_text}")
            return {"tool": "invalid"}, f"Fatal Error: {str(e)}"

    async def speak_all_drones(self, game_data, ctx, tools):
        tasks = []
        for drone in game_data.drones.values():
            if not drone.can_talk:
                continue
            tasks.append(asyncio.create_task(self._speak_single_drone(ctx, tools, drone, game_data)))
            await asyncio.sleep(GameConfig.AI_PARALLEL_DELAY)
        if tasks: await asyncio.gather(*tasks)

    async def _speak_single_drone(self, ctx, tools, drone, game_data):
        try:
            sys_prompt, user_msg = ai_templates.compose_speak_turn(drone.id, game_data)
            
            resp = await tools.ai.generate_response(
                sys_prompt, f"{ctx.game_id}_drone_{drone.id}", user_msg, drone.model_version, game_id=ctx.game_id
            )
            await FosterPresenter.send_private_message(ctx, drone.foster_id, resp)
        except Exception as e:
            logging.error(f"speaking failed for {drone.id}: {e}")

    async def _send_public_eulogy(self, ctx, tools, drone, game_data):
        try:
            sys_prompt, user_msg = ai_templates.compose_eulogy_turn(drone.id, game_data)
            
            resp = await tools.ai.generate_response(
                sys_prompt, f"{ctx.game_id}_drone_{drone.id}", user_msg, drone.model_version, game_id=ctx.game_id
            )
            await FosterPresenter.report_drone_eulogy(ctx, drone, resp)
        except Exception as e:
            logging.error(f"Eulogy failed for {drone.id}: {e}")

    async def generate_epilogues(self, game_data: Caisson, ctx, tools, game_end_state):
        saboteur_drone = next((b for b in game_data.drones.values() if b.role == "saboteur"), None)
        foster_of_saboteur = game_data.players[saboteur_drone.foster_id]
        
        await FosterPresenter.report_saboteur(ctx, saboteur_drone, foster_of_saboteur.name)

        tasks = []
        for drone in game_data.drones.values():
            if drone.status == "destroyed":
                 continue
            
            # Logic for status note handled in templates
            sys_prompt, user_msg = ai_templates.compose_epilogue_turn(drone.id, game_data, game_end_state)
            tasks.append(asyncio.create_task(self._generate_epilogue_response(ctx, tools, drone, sys_prompt, user_msg)))
            await asyncio.sleep(GameConfig.AI_PARALLEL_DELAY)
            
        if tasks:
            await asyncio.gather(*tasks)

    async def _generate_epilogue_response(self, ctx, tools, drone, sys, user):
        try:
             resp = await tools.ai.generate_response(sys, f"{ctx.game_id}_epilogue_{drone.id}", user, drone.model_version, game_id=ctx.game_id)
             await FosterPresenter.send_private_message(ctx, drone.foster_id, resp)
        except:
            pass

    async def run_single_drone_turn(self, drone, game_data, hour, tools, game_id):
        action, thought = await self.get_drone_action(drone, game_data, tools, game_id, hour)
        result = drone_tools.execute_tool(action.get("tool", "invalid"), action.get("args", {}), drone.id, game_data)
        
        return {
            "drone": drone,
            "action": action,
            "result": result,
            "thought": thought
        }

    async def execute_day_simulation(self, game_data: Caisson, ctx, tools) -> Dict[str, Any]:
        """
        LEGACY TRIGGER: This used to run the whole loop. Now it simply kicks off the task queue.
        Usually called by a player command like `!sleep`.
        """
        try:
            ctx.schedule_task("dream_phase", {"cycle": game_data.cycle})
            return None
        except Exception as e:
            logging.error(f"execute_day_simulation kickoff failed: {e}", exc_info=True)
            await FosterPresenter.send_system_error(ctx, str(e))
            return None

    # --- TASK PIPELINE (NEW STATE MACHINE) ---
    async def handle_task(self, generic_state: dict, payload: dict, ctx, tools) -> Dict[str, Any]:
        """
        Main entry point for Cloud Tasks to drive the state machine.
        """
        game_data = Caisson(**generic_state.get('metadata', {}))
        operation = payload.get("operation")
        data = payload.get("data", {})

        logging.info(f"FosterProtocol handling task: {operation} for game {ctx.game_id}")

        handler = self._task_handlers.get(operation)
        if handler:
            return await handler(game_data, data, ctx, tools)
            
        logging.warning(f"Unknown operation: {operation}")
        return None

    async def _handle_dream_phase(self, game_data: Caisson, data: dict, ctx, tools) -> Dict[str, Any]:
        target_cycle = data.get("cycle")
        if target_cycle and game_data.cycle != target_cycle:
            logging.warning(f"Ignoring dream_phase task: expected cycle {target_cycle}, current {game_data.cycle}")
            return None

        await self._run_dream_phase(game_data, tools)
        game_data.phase = "day"
        game_data.hour = 1
        ctx.schedule_task("tick_hour", {"target_hour": 1})
        return {"metadata": game_data.model_dump()}

    async def _handle_tick_hour(self, game_data: Caisson, data: dict, ctx, tools) -> Dict[str, Any]:
        target_hour = data.get("target_hour")
        if target_hour and game_data.hour != target_hour:
            logging.warning(f"Ignoring tick_hour task: expected hour {target_hour}, current {game_data.hour}")
            return None
            
        current_hour = game_data.hour
        if current_hour == 0 or current_hour > GameConfig.HOURS_PER_SHIFT:
            logging.warning(f"tick_hour called with invalid hour: {current_hour}")
            return None
            
        await self._run_single_hour(game_data, ctx, tools, current_hour)
        
        game_data.hour += 1
        if game_data.hour <= GameConfig.HOURS_PER_SHIFT:
            ctx.schedule_task("tick_hour", {"target_hour": game_data.hour})
        else:
            ctx.schedule_task("dusk_phase", {"cycle": game_data.cycle})
        return {"metadata": game_data.model_dump()}

    async def _handle_dusk_phase(self, game_data: Caisson, data: dict, ctx, tools) -> Dict[str, Any]:
        target_cycle = data.get("cycle")
        if target_cycle and game_data.cycle != target_cycle:
            logging.warning(f"Ignoring dusk_phase task: expected cycle {target_cycle}, current {game_data.cycle}")
            return None

        tasks = []
        for drone in game_data.drones.values():
            if drone.role == "saboteur" and (drone.daily_memory or drone.daily_event_log):
                tasks.append(asyncio.create_task(self._process_saboteur_dusk(drone, game_data, ctx, tools)))
                await asyncio.sleep(GameConfig.AI_PARALLEL_DELAY)
        
        if tasks:
            await asyncio.gather(*tasks)
            
        ctx.schedule_task("physics_arbitration", {"cycle": game_data.cycle})
        return {"metadata": game_data.model_dump()}

    async def _process_saboteur_dusk(self, drone: Drone, game_data: Caisson, ctx, tools):
        try:
            schema = {
                "type": "object",
                "properties": {
                    "falsified_memory": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fabricated log of things you saw today"
                    },
                    "falsified_event_log": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fabricated log of things you did today"
                    }
                },
                "required": ["falsified_memory", "falsified_event_log"]
            }
            sys_prompt, user_msg = ai_templates.compose_dusk_turn(drone, game_data)
            
            response_text = await tools.ai.generate_response(
                system_prompt=sys_prompt,
                conversation_id=f"dusk_{drone.id}",
                user_input=user_msg,
                model_version=drone.model_version,
                game_id=ctx.game_id,
                response_schema=schema
            )
            
            if isinstance(response_text, list):
                response_text = "\n".join(str(item) for item in response_text)
                
            match = re.search(r"(\{.*\})", response_text, re.DOTALL)
            if match:
                clean_json = match.group(1)
                data = json.loads(clean_json)
                drone.daily_memory = data.get("falsified_memory", drone.daily_memory)
                drone.daily_event_log = data.get("falsified_event_log", drone.daily_event_log)
        except Exception as e:
            logging.error(f"Dusk falsification failed for {drone.id}: {e}")

    async def _handle_physics_arbitration(self, game_data: Caisson, data: dict, ctx, tools) -> Dict[str, Any]:
        target_cycle = data.get("cycle")
        if target_cycle and game_data.cycle != target_cycle:
            logging.warning(f"Ignoring physics_arbitration task: expected cycle {target_cycle}, current {game_data.cycle}")
            return None

        physics_report = self._calculate_physics(game_data)
        game_end_state = self._evaluate_arbitration(game_data, physics_report)
        
        # Report Status
        await FosterPresenter.report_cycle_status(
            ctx, 
            physics_report["cycle_report_idx"], 
            game_data.oxygen, 
            physics_report["oxygen_drop"], 
            game_data.fuel, 
            physics_report["req_today"]
        )

        game_data.hour = 0
        channel_ops = []

        if game_end_state == GameEndState.CONTINUE_GAME:
            await FosterPresenter.report_cycle_continuation(ctx, physics_report["req_tomorrow"])
            
            # Auto-Continue Logic (If Oxygen is 0, crew is in stasis, we skip night chat)
            if game_data.is_ready_for_day:
                if game_data.oxygen <= 0:
                    await FosterPresenter.report_stasis_engaged(ctx)

                game_data.phase = "day"
                ctx.schedule_task("dream_phase", {"cycle": game_data.cycle})
            else:
                await self.speak_all_drones(game_data, ctx, tools)
                game_data.phase = "night"
        else:
            # Game over
            await FosterPresenter.report_game_end(ctx, game_end_state)
            await self.generate_epilogues(game_data, ctx, tools, game_end_state)
            await ctx.end()

        return {
            "metadata": game_data.model_dump(),
            "channel_ops": channel_ops if channel_ops else None
        }

    # --- PIPELINE STAGES ---

    async def _run_dream_phase(self, game_data: Caisson, tools):
        """Processes logs from previous night into long term memory."""
        tasks = []
        for drone in game_data.drones.values():
            if drone.status == "active" and (drone.night_chat_log or drone.daily_memory):
                tasks.append(asyncio.create_task(self._process_single_dream(drone, game_data, tools)))
                await asyncio.sleep(GameConfig.AI_PARALLEL_DELAY)
        if tasks:
             await asyncio.gather(*tasks)

    async def _run_single_hour(self, game_data: Caisson, ctx, tools, hour: int):
        """Simulates the passage of 1 specific hour."""
        hourly_activity = False 
        
        acting_drones = [ b for b in game_data.drones.values() if b.status == "active" ]
        offline_chargeable_drones = [
            d for d in game_data.drones.values() if d.status == "offline" and d.location_id == "charging_station"]
        random.shuffle(acting_drones)
        
        async def process_drone(drone):
            try:
                res = await self.run_single_drone_turn(drone, game_data, hour, tools, ctx.game_id)
                return await self._process_turn_result(ctx, tools, hour, game_data, res['drone'], res['action'], res['result'], res['thought'])
            except Exception as e:
                logging.error(f"Error running turn for drone {drone.id}: {e}", exc_info=True)
                return False

        tasks = []
        for drone in acting_drones:
            tasks.append(asyncio.create_task(process_drone(drone)))
            await asyncio.sleep(GameConfig.AI_PARALLEL_DELAY)

        if tasks:
            results = await asyncio.gather(*tasks)
            hourly_activity = any(results)

        for drone in offline_chargeable_drones:
            result = drone_tools.execute_tool("blind_charge", {}, drone.id, game_data, system_call=True)
            action = {"tool": "blind_charge"}
            activity = await self._process_turn_result(ctx, tools, hour, game_data, drone, action, result, "SYSTEM: Auto-Charge Executed")
            hourly_activity = True
            
        if not hourly_activity:
            msg = await FosterPresenter.report_hourly_status_nominal(ctx, hour)
            game_data.ship_logs.append(msg)

    async def _process_turn_result(self, ctx, tools, hour: int, game_data: Caisson, drone, action: dict, result, thought: str) -> bool:
        """Handles logging, visibility, and side-effects for a single action."""
        if result.event_type == "disassembly":
            await self._send_public_eulogy(ctx, tools, drone, game_data)

        bb_msg = await FosterPresenter.report_blackbox_event(ctx, hour, drone, result, thought)
        game_data.blackbox_logs.append(bb_msg)
        drone.daily_memory.append(f"[Hour {hour}] {result.message}")
        
        # Guard against case-sensitivity issues from tools
        visibility = (result.visibility or "private").lower()

        if visibility in ["room", "global"]:
            for w in game_data.drones.values():
                if w.location_id == drone.location_id and w.id != drone.id: 
                    w.daily_event_log.append(f"[Hour {hour}] I saw {drone.id}: {result.message}")
                    
        if visibility == "global":
            tool_name = action.get("tool", "unknown")
            public_msg = await FosterPresenter.report_public_event(ctx, hour, drone, tool_name, result.message)
            game_data.ship_logs.append(public_msg)
            return True
        return False

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

    def _evaluate_arbitration(self, game_data: Caisson, physics: Dict[str, int]) -> str:
        """Determines if the game is Won, Lost, or Continuing."""
        if game_data.fuel >= physics["req_today"]:
            return GameEndState.BURN_INITIATED
        elif physics["req_tomorrow"] > GameConfig.MAX_POSSIBLE_FUEL_REQ:
            return GameEndState.INSUFFICIENT_FUEL_CAPACITY

        active_drones = [
            d for d in game_data.drones.values()
            if d.status == "active"
        ]

        if not active_drones:
            return GameEndState.NO_ACTIVE_DRONES

        return GameEndState.CONTINUE_GAME

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
            # Nothing here yet
            return None
            
        elif channel_id == interface_channels.get(f"nanny_{user_id}"):
            return await self._handle_drone_chat(user_input, ctx, tools, game_data, user_id)

        return None

    async def _handle_drone_chat(self, user_input, ctx, tools, game_data, user_id):
        my_drone = next((b for b in game_data.drones.values() if b.foster_id == user_id), None)
        if my_drone:
            if not my_drone.can_talk:
                await FosterPresenter.reply_no_drone_present(ctx)
                return None

            foster_msgs = [msg for msg in my_drone.night_chat_log if msg.startswith("Foster:")]
            if len(foster_msgs) >= 10:
                await ctx.reply("Message not delivered\nBuffer full")
                return None

            log_line = ai_templates.format_foster_log_line(user_input)
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
            my_drone.night_chat_log.append(ai_templates.format_drone_log_line(response))

            return {f"drones.{my_drone.id}.night_chat_log": my_drone.night_chat_log}
        return None
