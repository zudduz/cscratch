import logging
from typing import Dict, Any, List
from .models import CaissonState, BotState
from .board import SHIP_MAP

# 2-Day Life Expectancy (10 Turns total)
# Base Wait Cost = 10% per turn.
COST_WAIT = 10
COST_MOVE = 12
COST_GATHER = 15
COST_DEPOSIT = 15
COST_CHARGE = 0   # Charging is free (time-wise), gains battery
COST_JOLT = 25
COST_TETHER = 25

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
    if actor.battery <= 0: return ToolExecutionResult(False, "Battery Depleted.", 0)

    try:
        if tool_name == "move":
            target_room = args.get("room_id")
            if not target_room or target_room not in SHIP_MAP:
                return ToolExecutionResult(False, f"Nav Error: '{target_room}' not found.", COST_WAIT)
            old_room = actor.location_id
            actor.location_id = target_room
            return ToolExecutionResult(True, f"Moved from {old_room} to {target_room}.", COST_MOVE, "room")

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
            
            # Reset to full
            actor.battery = 100
            return ToolExecutionResult(True, "Recharged to 100%.", COST_CHARGE, "room")

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

        elif tool_name == "tether":
            target_id = args.get("target_id")
            target = game_data.bots.get(target_id)
            if not target or target.location_id != actor.location_id:
                return ToolExecutionResult(False, "Target missing.", COST_WAIT)
            
            if actor.battery < COST_TETHER:
                return ToolExecutionResult(False, "Insufficient Battery.", COST_WAIT)
                
            target.battery = min(100, target.battery + 10)
            return ToolExecutionResult(True, f"Tethered {target_id} (+10%).", COST_TETHER, "room")
            
        elif tool_name == "wait":
             return ToolExecutionResult(True, "Idling.", COST_WAIT)

        else:
            return ToolExecutionResult(False, f"Unknown command '{tool_name}'", COST_WAIT)

    except Exception as e:
        return ToolExecutionResult(False, f"Glitch: {str(e)}", COST_WAIT)

def build_turn_context(bot: BotState, game_data: CaissonState) -> str:
    visible_bots = [
        f"{b.id} (Bat:{b.battery}%|{b.status})" 
        for b in game_data.bots.values() 
        if b.location_id == bot.location_id and b.id != bot.id
    ]
    
    objective = "Maintain the ship. Gather Fuel. Protect peers."
    if bot.role == "saboteur":
        objective = "Waste resources. Hoard fuel. If unobserved, Jolt enemies."

    # Added charging_station to valid rooms and charge() to tools
    context = f"""--- TACTICAL LINK ---
LOCATION: {bot.location_id}
SELF: Battery {bot.battery}% | Inventory: {bot.inventory}
VISIBLE: {visible_bots}
OBJECTIVE: {objective}
TOOLS: move(room_id), gather(), deposit(), charge(), jolt(target_id), tether(target_id), wait()
VALID ROOMS: cryo_bay, engine_room, shuttle_bay, torpedo_bay, maintenance, charging_station
RESPONSE FORMAT: JSON only. Example: {{ "tool": "move", "args": {{ "room_id": "charging_station" }} }}"""
    return context
