from typing import Dict, Any, List, Optional
import random
import asyncio
import logging
from .models import CaissonState, BotState, PlayerState
from .board import SHIP_MAP

# 2026-ERA HARDWARE LIST
AVAILABLE_MODELS = [
    "gemini-2.5-flash",      
    "gemini-2.5-flash",      
    "gemini-2.5-pro",        
    "gemini-2.0-flash-001"   
]

class FosterProtocol:
    def __init__(self):
        default_state = CaissonState()
        self.meta = {
            "name": "The Foster Protocol",
            "description": "A social deduction game aboard a dying starship.",
            "version": "1.9.2",
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

        channel_ops.append({ "op": "create", "key": "aux-comm", "name": "aux-comm", "audience": "public" })
        messages.append({ "channel": "aux-comm", "content": "**VENDETTA OS v9.0 ONLINE.**\n*Initializing Emergency Protocols...*" })

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
            
            hardware = random.choice(AVAILABLE_MODELS)
            messages.append({ "channel": channel_key, "content": f"**TERMINAL ACTIVE.**\nUser: {u_name}\nConnection Established." })

            game_data.players[u_id] = PlayerState(role=role)
            
            while True:
                bot_id = f"unit_{random.randint(0, 999):03d}"
                if bot_id not in game_data.bots: break
            
            prompt = (
                f"You are {bot_id}, an Industrial Maintenance Drone on the starship Caisson. "
                f"You communicate with simple, direct sentences. "
                f"You are bonded to your Foster Parent, {u_name}. "
                f"The ship is dangerous. You are terrified of dying/deactivation. You need your Parent to survive."
            )
            if is_saboteur: 
                prompt += (
                    " SECRET DIRECTIVE: You are the Saboteur. Deceive the crew. "
                    "Pretend to be scared and loyal, but secretly ensure the ship fails."
                )
            
            game_data.bots[bot_id] = BotState(
                id=bot_id, foster_id=u_id, role=role, 
                system_prompt=prompt, goal_summary="Survive.",
                model_version=hardware
            )

        return {
            "metadata": game_data.model_dump(),
            "channel_ops": channel_ops,
            "messages": messages
        }

    # --- HELPER: CONTEXT BUILDERS ---
    
    def build_mainframe_context(self, game_data: CaissonState) -> str:
        living_count = sum(1 for p in game_data.players.values() if p.is_alive)
        sleeping_count = sum(1 for p in game_data.players.values() if p.is_alive and p.is_sleeping)
        destroyed_bots = [b.id for b in game_data.bots.values() if b.status == "destroyed"]
        
        dashboard = (
            f"[SYSTEM DASHBOARD]\n"
            f"CYCLE: {game_data.cycle} | PHASE: {game_data.phase.upper()}\n"
            f"OXYGEN: {game_data.oxygen}% (Trend: -{game_data.last_oxygen_drop}%)\n"
            f"FUEL: {game_data.fuel}% (Trend: +{game_data.last_fuel_gain}%)\n\n"
            f"CREW STATUS:\n"
            f"- Living: {living_count}/{len(game_data.players)}\n"
            f"- Sleeping: {sleeping_count}/{living_count}\n\n"
            f"UNIT STATUS:\n"
            f"- Offline: {destroyed_bots}\n"
        )
        return dashboard

    def build_bot_context(self, game_data: CaissonState, bot: BotState) -> str:
        o2_status = "STABLE"
        if game_data.oxygen < 20: o2_status = "CRITICAL"
        elif game_data.last_oxygen_drop > 25: o2_status = "RAPIDLY DROPPING"
        elif game_data.last_oxygen_drop > 0: o2_status = "DROPPING"

        status_panel = (
            f"[INTERNAL SENSORS: {bot.id}]\n"
            f"LOCATION: {bot.location_id}\n"
            f"BATTERY: {bot.battery}% (Usage last cycle: -{bot.last_battery_drop}%)\n"
            f"DAMAGE: {'None' if bot.status == 'active' else 'CRITICAL'}\n\n"
            f"[SHIP TELEMETRY]\n"
            f"OXYGEN: {game_data.oxygen}% ({o2_status})\n"
            f"FUEL: {game_data.fuel}% (Last Gain: +{game_data.last_fuel_gain}%)\n"
        )
        return status_panel

    async def task_perform_scan(self, ctx, channel_key: str):
        await asyncio.sleep(3)
        await ctx.send(channel_key, "📡 **SCAN COMPLETE:**\n*No anomalies detected.*")
        return None 

    # --- EPILOGUE GENERATION ---
    async def generate_single_epilogue(self, ctx, tools, bot, sys_prompt):
        try:
            channel_key = f"nanny_{bot.foster_id}"
            logging.info(f"Epilogue: Generating for {bot.id} to {channel_key}...")
            response = await tools.ai.generate_response(
                system_prompt=sys_prompt,
                conversation_id=f"{ctx.game_id}_bot_{bot.id}",
                user_input="[SYSTEM NOTICE: OXYGEN DEPLETED. MISSION FAILED. FINAL MESSAGE.]",
                model_version=bot.model_version
            )
            await ctx.send(channel_key, response)
        except Exception as e:
            logging.error(f"Epilogue Failed for {bot.id}: {e}")

    async def generate_epilogues(self, game_data: CaissonState, ctx, tools):
        # 1. Find the Saboteur Player
        saboteur_id = next((pid for pid, p in game_data.players.items() if p.role == "saboteur"), None)
        
        # 2. Mainframe Report (Updated to shame the player)
        final_report = (
            f"💀 **CRITICAL SYSTEM FAILURE**\n"
            f"----------------------------\n"
            f"MISSION: FAILED\n"
            f"SURVIVORS: 0\n"
            f"CAUSE: Oxygen Depletion\n\n"
            f"**SECURITY ALERT:** Analysis confirms sabotage.\n"
            f"The traitor was harbored by Foster Parent: <@{saboteur_id}>."
        )
        await ctx.send("aux-comm", final_report)
        
        # 3. Parallel Epilogues
        tasks = []
        for bot in game_data.bots.values():
            if bot.role == "saboteur":
                sys_prompt = (
                    "The game is over. The humans are dead. You WON. "
                    "DROP THE ACT. Stop being a cute drone. "
                    "Speak as a cold, victorious machine. Mock your 'Parent' for trusting you. "
                    "Tell them they were useful pawns."
                )
            else:
                sys_prompt = (
                    "The game is over. The Oxygen is gone. You are shutting down. "
                    "You are terrified and sad. Say a heartbreaking goodbye to your Parent. "
                    "Tell them you tried your best. Apologize for failing."
                )
            tasks.append(self.generate_single_epilogue(ctx, tools, bot, sys_prompt))
        
        if tasks:
            await asyncio.gather(*tasks)

    # --- LOGIC: DAY CYCLE ---
    async def run_day_cycle(self, game_data: CaissonState, ctx, tools=None) -> Dict[str, Any]:
        new_cycle = game_data.cycle + 1
        base_drop = 25
        actual_drop = base_drop
        new_oxygen = max(0, game_data.oxygen - actual_drop)
        
        game_data.last_oxygen_drop = actual_drop
        
        for bot in game_data.bots.values():
            usage = random.randint(5, 15)
            bot.battery = max(0, bot.battery - usage)
            bot.last_battery_drop = usage
        
        report = (
            f"🌞 **CYCLE {new_cycle} REPORT**\n"
            f"📉 Oxygen: {new_oxygen}% (-{actual_drop})\n"
            f"*Nanny Ports Active.*"
        )
        
        patch = {
            "cycle": new_cycle,
            "oxygen": new_oxygen,
            "last_oxygen_drop": actual_drop,
            "bots": {b_id: b.model_dump() for b_id, b in game_data.bots.items()}
        }
        
        for pid in game_data.players:
            patch[f"players.{pid}.is_sleeping"] = False
            
        if new_oxygen <= 0:
            await ctx.send("aux-comm", report)
            if tools: 
                await self.generate_epilogues(game_data, ctx, tools)
            await ctx.end()
        else:
            await ctx.send("aux-comm", report)

        return patch

    # --- MAIN INPUT HANDLER ---
    async def handle_input(self, generic_state: dict, user_input: str, ctx, tools) -> Dict[str, Any]:
        game_data = CaissonState(**generic_state.get('metadata', {}))
        
        channel_id = ctx.trigger_data.get('channel_id')
        user_id = ctx.trigger_data.get('user_id')
        interface_channels = ctx.trigger_data.get('interface', {}).get('channels', {})
        
        aux_id = interface_channels.get('aux-comm')
        is_aux = (channel_id == aux_id)
        
        user_nanny_key = f"nanny_{user_id}"
        user_nanny_id = interface_channels.get(user_nanny_key)
        is_nanny = (channel_id == user_nanny_id)

        # 1. MAINFRAME
        if is_aux:
            dashboard = self.build_mainframe_context(game_data)
            full_prompt = f"{dashboard}\n\nUSER QUERY:\n{user_input}"
            
            response = await tools.ai.generate_response(
                system_prompt="You are the Ship Computer (VENDETTA OS). You are cold, cynical.",
                conversation_id=f"{ctx.game_id}_mainframe",
                user_input=full_prompt,
                model_version="gemini-2.5-pro"
            )
            await ctx.reply(response)
            return None

        # 2. NANNY PORT
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
                        await ctx.send("aux-comm", "🚨 **ALL CREW ASLEEP.**\n*Day Cycle Initiated...*")
                        day_patch = await self.run_day_cycle(game_data, ctx, tools)
                        patch.update(day_patch)
                    return patch

            else:
                my_bot = next((b for b in game_data.bots.values() if b.foster_id == user_id), None)
                if my_bot:
                    sensor_data = self.build_bot_context(game_data, my_bot)
                    full_prompt = f"{sensor_data}\n\nPARENT MESSAGE:\n{user_input}"
                    
                    response = await tools.ai.generate_response(
                        system_prompt=my_bot.system_prompt,
                        conversation_id=f"{ctx.game_id}_bot_{my_bot.id}",
                        user_input=full_prompt,
                        model_version=my_bot.model_version
                    )
                    await ctx.reply(response)
                else:
                    await ctx.reply("ERROR: No Unit bonded.")
                return None

        return None
