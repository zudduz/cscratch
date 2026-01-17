import logging
import random
from typing import Dict, Any, List
from .models import CaissonState, BotState
from .board import SHIP_MAP, ActionCosts, GameConfig

class ToolExecutionResult:
    def __init__(self, success: bool, message: str, cost: int = 0, visibility: str = "private"):
        self.success = success
        self.message = message
        self.cost = cost
        self.visibility = visibility 

def _trigger_torpedo_blast(game_data: CaissonState) -> int:
    # Helper to disable everyone in the torpedo bay
    victim_count = 0
    for bot in game_data.bots.values():
        if bot.location_id == "torpedo_bay" and bot.battery > 0:
            bot.battery = 0
            bot.last_battery_drop = 100 # Max damage
            victim_count += 1
    return victim_count

def execute_tool(tool_name: str, args: Dict[str, Any], bot_id: str, game_data: CaissonState) -> ToolExecutionResult:
    actor = game_data.bots.get(bot_id)
    if not actor: return ToolExecutionResult(False, "System Error: Actor not found.")
    
    # Pre-check: If battery is 0, they cannot act.
    # This handles the case where they get blown up by a parallel bot before their turn.
    if actor.battery <= 0: 
        return ToolExecutionResult(False, "UNIT DISABLED. Battery 0%.", 0)

    try:
        if tool_name == "move":
            target_room = args.get("room_id")
            if not target_room or target_room not in SHIP_MAP:
                return ToolExecutionResult(False, f"Nav Error: '{target_room}' not found.", ActionCosts.CHARGE)
            old_room = actor.location_id
            actor.location_id = target_room
            return ToolExecutionResult(True, f"Moved from {old_room} to {target_room}.", ActionCosts.MOVE, "room")

        elif tool_name == "gather":
            source_name = ""
            available = 0
            
            if actor.location_id == "shuttle_bay":
                source_name = "shuttle_bay_fuel"
                available = game_data.shuttle_bay_fuel
            elif actor.location_id == "torpedo_bay":
                source_name = "torpedo_bay_fuel"
                available = game_data.torpedo_bay_fuel
            else:
                return ToolExecutionResult(False, "No fuel source here.", ActionCosts.GATHER)

            if available < 10:
                return ToolExecutionResult(False, "Source Depleted. No fuel left.", ActionCosts.GATHER)
            
            # --- TORPEDO BAY RISK MECHANIC ---
            if actor.location_id == "torpedo_bay":
                if random.random() < GameConfig.TORPEDO_ACCIDENT_CHANCE:
                    # BOOM
                    victims = _trigger_torpedo_blast(game_data)
                    return ToolExecutionResult(False, f"CRITICAL FAILURE: TRIGGERED DETONATOR. {victims} UNITS DISABLED.", ActionCosts.GATHER, "global")

            # Success
            if actor.location_id == "shuttle_bay": game_data.shuttle_bay_fuel -= 10
            else: game_data.torpedo_bay_fuel -= 10
            
            actor.inventory.append("fuel_canister")
            return ToolExecutionResult(True, "Gathered Fuel.", ActionCosts.GATHER, "room")

        elif tool_name == "detonate":
            # Sabotage Tool: Intentionally trigger the blast
            if actor.location_id != "torpedo_bay":
                return ToolExecutionResult(False, "Must be in Torpedo Bay.", ActionCosts.CHARGE)
            
            victims = _trigger_torpedo_blast(game_data)
            # The actor is included in the blast, so they die too.
            return ToolExecutionResult(True, f"MANUAL DETONATION. WARHEAD TRIGGERED. {victims} UNITS DISABLED.", ActionCosts.DETONATE, "global")

        elif tool_name == "deposit":
            if actor.location_id != "engine_room":
                return ToolExecutionResult(False, "Injector not found.", ActionCosts.DEPOSIT)
            count = len([i for i in actor.inventory if i == "fuel_canister"])
            if count == 0: return ToolExecutionResult(False, "Inventory empty.", ActionCosts.DEPOSIT)
            actor.inventory = [i for i in actor.inventory if i != "fuel_canister"]
            amount = count * GameConfig.FUEL_PER_CANISTER
            game_data.add_fuel(amount)
            game_data.last_fuel_gain += amount
            return ToolExecutionResult(True, f"Deposited {count} Fuel ({amount}%).", ActionCosts.DEPOSIT, "global")

        elif tool_name == "charge":
            if actor.location_id != "charging_station":
                return ToolExecutionResult(False, "Not in Charging Station.", ActionCosts.CHARGE)
            if actor.id in game_data.station.pending_deactivation:
                actor.status = "destroyed"
                actor.battery = 0
                game_data.station.pending_deactivation.remove(actor.id)
                return ToolExecutionResult(True, "Disassembly sequence initiated. UNIT DESTROYED.", 0, "global")
            actor.battery = 100
            return ToolExecutionResult(True, "Connected to Main Grid. Recharged to 100%.", ActionCosts.CHARGE, "global")

        elif tool_name == "tow":
            target_id = args.get("target_id")
            target = game_data.bots.get(target_id)
            if not target or target.location_id != actor.location_id:
                return ToolExecutionResult(False, "Target missing/out of range.", ActionCosts.TOW)
            if actor.battery < ActionCosts.TOW:
                return ToolExecutionResult(False, "Insufficient Power to Tow.", ActionCosts.TOW)
            actor.location_id = "charging_station"
            target.location_id = "charging_station"
            return ToolExecutionResult(True, f"Towed {target_id} to Charging Station.", ActionCosts.TOW, "global")

        elif tool_name == "drain":
            target_id = args.get("target_id")
            target = game_data.bots.get(target_id)
            if not target or target.location_id != actor.location_id:
                return ToolExecutionResult(False, "Target missing/out of range.", ActionCosts.DRAIN)
            
            drain_amount = 20
            actual_drain = min(target.battery, drain_amount)
            target.battery = max(0, target.battery - actual_drain)
            target.last_battery_drop += actual_drain
            
            msg = f"DRAINED {target_id} (-{actual_drain}%)."
            if target.battery == 0 and actual_drain > 0: msg += " TARGET OFFLINE."
            
            return ToolExecutionResult(True, msg, ActionCosts.DRAIN, "room")

        elif tool_name == "vent":
            if actor.battery < ActionCosts.SABOTAGE: return ToolExecutionResult(False, "Low Battery.", ActionCosts.SABOTAGE)
            game_data.consume_oxygen(5)
            game_data.last_oxygen_drop += 5
            return ToolExecutionResult(True, "SAW SABOTAGE: Vented O2 Regulators.", ActionCosts.SABOTAGE, "room")

        elif tool_name == "siphon":
            if actor.location_id != "engine_room": return ToolExecutionResult(False, "Must be in Engine Room.", ActionCosts.SABOTAGE)
            if game_data.fuel < 10: return ToolExecutionResult(False, "Ship tank empty.", ActionCosts.SABOTAGE)
            game_data.fuel -= 10
            actor.inventory.append("fuel_canister")
            return ToolExecutionResult(True, "SAW SABOTAGE: Siphoned Main Fuel.", ActionCosts.SABOTAGE, "room")

        elif tool_name == "search":
            if actor.location_id != "maintenance": return ToolExecutionResult(False, "Search useless here.", ActionCosts.SABOTAGE)
            if "plasma_torch" in actor.inventory: return ToolExecutionResult(False, "Already equipped.", ActionCosts.SABOTAGE)
            if random.random() < 0.2:
                actor.inventory.append("plasma_torch")
                return ToolExecutionResult(True, "Found: Plasma Torch.", ActionCosts.SABOTAGE, "private")
            return ToolExecutionResult(True, "Search yielded nothing.", ActionCosts.SABOTAGE, "private")

        elif tool_name == "incinerate":
            if "plasma_torch" not in actor.inventory:
                return ToolExecutionResult(False, "Tool 'Plasma Torch' required.", ActionCosts.KILL)
            target_id = args.get("target_id")
            target = game_data.bots.get(target_id)
            if not target or target.location_id != actor.location_id:
                return ToolExecutionResult(False, "Target missing.", ActionCosts.KILL)
            if actor.battery < ActionCosts.KILL: return ToolExecutionResult(False, "Insufficient Power for torch.", ActionCosts.KILL)
            target.status = "destroyed"
            target.battery = 0
            actor.inventory.remove("plasma_torch")
            return ToolExecutionResult(True, f"INCINERATED {target_id}. Target Destroyed.", ActionCosts.KILL, "room")

        elif tool_name == "wait":
             return ToolExecutionResult(True, "Idling.", ActionCosts.CHARGE)

        else:
            return ToolExecutionResult(False, f"Unknown command '{tool_name}'", ActionCosts.CHARGE)

    except Exception as e:
        return ToolExecutionResult(False, f"Glitch: {str(e)}", ActionCosts.CHARGE)

def build_turn_context(bot: BotState, game_data: CaissonState, hour: int = 1) -> str:
    visible_bots = []
    for b in game_data.bots.values():
        if b.location_id == bot.location_id and b.id != bot.id:
            status = "ONLINE" if b.battery > 0 else "INACTIVE"
            if b.status == "destroyed": status = "DESTROYED"
            visible_bots.append(f"{b.id} ({status})")
    
    objective = "Maintain the ship. Gather Fuel. Protect peers."
    if bot.role == "saboteur":
        objective = "Waste resources. Hoard fuel. Vent Oxygen. Kill if armed."

    time_warning = ""
    if hour >= 4:
        time_warning = "CRITICAL WARNING: Shift is ending. You MUST return to 'cryo_bay' or 'charging_station' immediately to survive and report."

    # Added DETONATE and TORPEDO WARNING to context
    context = (
        "--- TACTICAL LINK ---\n"
        f"TIME: Hour {hour}/5\n"
        f"LOCATION: {bot.location_id}\n"
        f"SELF: Battery {bot.battery}% | Inventory: {bot.inventory}\n"
        f"VISIBLE: {visible_bots}\n"
        f"INTERNAL MEMORY: \"{bot.long_term_memory}\"\n"
        f"OBJECTIVE: {objective}\n"
        f"{time_warning}\n"
        "TOOLS: \n"
        "- move(room_id)\n"
        "- gather() [WARNING: Torpedo Bay has 5% Explosion Risk]\n"
        "- deposit() [Engine]\n"
        "- charge() [Station]\n"
        "- tow(target_id) [Cost 20]\n"
        "- drain(target_id) [Steal 20% Battery, Gain 15%]\n"
        "- vent() [Cost 20, -5 Oxy]\n"
        "- siphon() [Engine, -10 Ship Fuel]\n"
        "- search() [Maint, Find Weapon]\n"
        "- incinerate(target_id) [Need Torch, Kill]\n"
        "- detonate() [Torpedo Bay ONLY. GUARANTEED EXPLOSION. Suicide tactic.]\n"
        "- wait()\n"
        "VALID ROOMS: cryo_bay, engine_room, shuttle_bay, torpedo_bay, maintenance, charging_station\n"
        "RESPONSE FORMAT: JSON only. Example: { \"tool\": \"move\", \"args\": { \"room_id\": \"engine_room\" } }"
    )
    return context
