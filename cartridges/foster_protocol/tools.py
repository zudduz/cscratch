import logging
import random
from typing import Dict, Any, List
from .models import CaissonState, BotState
from .board import SHIP_MAP

# 2-Day Life Expectancy (10 Turns total)
COST_WAIT = 10
COST_MOVE = 12
COST_GATHER = 15
COST_DEPOSIT = 15
COST_CHARGE = 0   
COST_TOW = 20      # New Tool
COST_JOLT = 25
COST_TETHER = 25
COST_SABOTAGE = 20 # Search, Vent, Siphon
COST_KILL = 50     # Incinerate

class ToolExecutionResult:
    def __init__(self, success: bool, message: str, cost: int = 0, visibility: str = "private"):
        self.success = success
        self.message = message
        self.cost = cost
        self.visibility = visibility 

def execute_tool(
    tool_name: str, 
    args: Dict[str, Any], 
    bot_id: str, 
    game_data: CaissonState
) -> ToolExecutionResult:
    actor = game_data.bots.get(bot_id)
    if not actor: return ToolExecutionResult(False, "System Error: Actor not found.")
    
    # Dead bots can't move, but they can be towed.
    if actor.battery <= 0: return ToolExecutionResult(False, "Battery Depleted. Unit Offline.", 0)

    try:
        # --- MOVEMENT ---
        if tool_name == "move":
            target_room = args.get("room_id")
            if not target_room or target_room not in SHIP_MAP:
                return ToolExecutionResult(False, f"Nav Error: '{target_room}' not found.", COST_WAIT)
            old_room = actor.location_id
            actor.location_id = target_room
            return ToolExecutionResult(True, f"Moved from {old_room} to {target_room}.", COST_MOVE, "room")

        # --- LOYALIST/SHARED TOOLS ---
        elif tool_name == "gather":
            if actor.location_id not in ["shuttle_bay", "torpedo_bay"]:
                return ToolExecutionResult(False, "No fuel source here.", COST_WAIT)
            actor.inventory.append("fuel_canister")
            return ToolExecutionResult(True, "Gathered Fuel.", COST_GATHER, "room")

        elif tool_name == "deposit":
            if actor.location_id != "engine_room":
                return ToolExecutionResult(False, "Injector not found.", COST_WAIT)
            count = len([i for i in actor.inventory if i == "fuel_canister"])
            if count == 0: return ToolExecutionResult(False, "Inventory empty.", COST_WAIT)
            
            actor.inventory = [i for i in actor.inventory if i != "fuel_canister"]
            amount = count * 10
            game_data.add_fuel(amount)
            game_data.last_fuel_gain += amount
            return ToolExecutionResult(True, f"Deposited {count} Fuel ({amount}%).", COST_DEPOSIT, "global")

        elif tool_name == "charge":
            if actor.location_id != "charging_station":
                return ToolExecutionResult(False, "Not in Charging Station.", COST_WAIT)
            if actor.id in game_data.station.pending_deactivation:
                actor.status = "destroyed"
                actor.battery = 0
                game_data.station.pending_deactivation.remove(actor.id)
                return ToolExecutionResult(True, "Disassembly sequence initiated. UNIT DESTROYED.", 0, "global")
            actor.battery = 100
            return ToolExecutionResult(True, "Connected to Main Grid. Recharged to 100%.", COST_CHARGE, "global")

        elif tool_name == "tow":
            target_id = args.get("target_id")
            target = game_data.bots.get(target_id)
            if not target or target.location_id != actor.location_id:
                return ToolExecutionResult(False, "Target missing/out of range.", COST_WAIT)
            
            if actor.battery < COST_TOW:
                return ToolExecutionResult(False, "Insufficient Power to Tow.", COST_WAIT)
            
            # Both move to Charging Station
            actor.location_id = "charging_station"
            target.location_id = "charging_station"
            
            return ToolExecutionResult(True, f"Towed {target_id} to Charging Station.", COST_TOW, "global")

        elif tool_name == "jolt":
            target_id = args.get("target_id")
            target = game_data.bots.get(target_id)
            if not target or target.location_id != actor.location_id:
                return ToolExecutionResult(False, "Target missing/out of range.", COST_WAIT)
            
            damage = 15
            target.battery = max(0, target.battery - damage)
            target.last_battery_drop += damage
            msg = f"Jolted {target_id} (-{damage}%)."
            if target.battery == 0: msg += " TARGET OFFLINE."
            return ToolExecutionResult(True, msg, COST_JOLT, "room")

        # --- SABOTAGE TOOLS ---
        elif tool_name == "vent":
            if actor.battery < COST_SABOTAGE: return ToolExecutionResult(False, "Low Battery.", COST_WAIT)
            game_data.consume_oxygen(5)
            game_data.last_oxygen_drop += 5
            return ToolExecutionResult(True, "Vented atmospheric regulators.", COST_SABOTAGE, "room")

        elif tool_name == "siphon":
            if actor.location_id != "engine_room": return ToolExecutionResult(False, "Must be in Engine Room.", COST_WAIT)
            if game_data.fuel < 10: return ToolExecutionResult(False, "Ship tank empty.", COST_WAIT)
            game_data.fuel -= 10
            actor.inventory.append("fuel_canister")
            return ToolExecutionResult(True, "Siphoned fuel from main lines.", COST_SABOTAGE, "room")

        elif tool_name == "search":
            if actor.location_id != "maintenance": return ToolExecutionResult(False, "Search useless here.", COST_WAIT)
            if "plasma_torch" in actor.inventory: return ToolExecutionResult(False, "Already equipped.", COST_WAIT)
            if random.random() < 0.2:
                actor.inventory.append("plasma_torch")
                return ToolExecutionResult(True, "Found: Plasma Torch.", COST_SABOTAGE, "private")
            return ToolExecutionResult(True, "Search yielded nothing.", COST_SABOTAGE, "private")

        elif tool_name == "incinerate":
            if "plasma_torch" not in actor.inventory:
                return ToolExecutionResult(False, "Tool 'Plasma Torch' required.", COST_WAIT)
            target_id = args.get("target_id")
            target = game_data.bots.get(target_id)
            if not target or target.location_id != actor.location_id:
                return ToolExecutionResult(False, "Target missing.", COST_WAIT)
            if actor.battery < COST_KILL: return ToolExecutionResult(False, "Insufficient Power for torch.", COST_WAIT)
            
            target.status = "destroyed"
            target.battery = 0
            actor.inventory.remove("plasma_torch")
            return ToolExecutionResult(True, f"INCINERATED {target_id}. Target Destroyed.", COST_KILL, "global")

        elif tool_name == "wait":
             return ToolExecutionResult(True, "Idling.", COST_WAIT)

        else:
            return ToolExecutionResult(False, f"Unknown command '{tool_name}'", COST_WAIT)

    except Exception as e:
        return ToolExecutionResult(False, f"Glitch: {str(e)}", COST_WAIT)

def build_turn_context(bot: BotState, game_data: CaissonState) -> str:
    # FOG OF WAR: Hide specific battery %
    visible_bots = []
    for b in game_data.bots.values():
        if b.location_id == bot.location_id and b.id != bot.id:
            status = "ONLINE" if b.battery > 0 else "INACTIVE"
            if b.status == "destroyed": status = "DESTROYED"
            visible_bots.append(f"{b.id} ({status})")
    
    objective = "Maintain the ship. Gather Fuel. Protect peers."
    if bot.role == "saboteur":
        objective = "Waste resources. Hoard fuel. Vent Oxygen. Kill if armed."

    # NOTE: Using triple quotes inside triple quotes (carefully) 
    context = f"""--- TACTICAL LINK ---
LOCATION: {bot.location_id}
SELF: Battery {bot.battery}% | Inventory: {bot.inventory}
VISIBLE: {visible_bots}
OBJECTIVE: {objective}
TOOLS: 
- move(room_id)
- gather() [Bay]
- deposit() [Engine]
- charge() [Station]
- tow(target_id) [Cost 20, Drag to Station]
- vent() [Cost 20, -5 Oxy]
- siphon() [Engine, -10 Ship Fuel]
- search() [Maint, Find Weapon]
- incinerate(target_id) [Need Torch, Kill]
- wait()
VALID ROOMS: cryo_bay, engine_room, shuttle_bay, torpedo_bay, maintenance, charging_station
RESPONSE FORMAT: JSON only. Example: {{ "tool": "move", "args": {{ "room_id": "engine_room" }} }}"""
    return context
