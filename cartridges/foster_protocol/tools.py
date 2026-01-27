import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional, List

# Assuming these exist in your project structure
from .models import Caisson, Drone
from .board import SHIP_MAP, ActionCosts, GameConfig

@dataclass
class ToolExecutionResult:
    success: bool
    message: str
    cost: int = 0
    visibility: str = "private"

@dataclass
class ToolContext:
    """Encapsulates the state required to execute a tool."""
    game_data: Caisson
    actor: Drone
    args: Dict[str, Any]

# --- Helpers ---

def _trigger_torpedo_blast(game_data: Caisson) -> None:
    """Helper to handle the EMP blast effect in the Torpedo Bay."""
    for drone in game_data.drones.values():
        if drone.location_id == "torpedo_bay":
            drone.battery = 0

def get_visible_drones(game_data: Caisson, location_id: str) -> List[str]:
    """Return a list of drone status strings visible in the given location."""
    return [
        f"{d.id} ({d.status})"
        for d in game_data.drones.values() 
        if d.location_id == location_id
    ]

# --- Base Class ---

class BaseTool(ABC):
    """Abstract base class for all drone tools."""
    name: str = "base"
    cost: int = 0
    required_location: Optional[str] = None 
    description: str = ""

    def run(self, context: ToolContext) -> ToolExecutionResult:
        if context.actor.battery <= 0:
            return ToolExecutionResult(False, "UNIT OFFLINE. Battery 0%.", 0)
        
        if self.required_location and self.required_location != context.actor.location_id:
            return ToolExecutionResult(
                False, 
                f"Action requires being in {self.required_location}.", 
                ActionCosts.WAIT
            )
        
        if context.actor.battery < self.cost:
            return ToolExecutionResult(False, "Insufficient Battery Level.", ActionCosts.WAIT)

        is_valid, error_msg = self.validate(context)
        if not is_valid:
             return ToolExecutionResult(False, error_msg, self.cost)

        result = self.execute(context)
        
        context.actor.battery = max(0, min(100, context.actor.battery - result.cost))
             
        return result

    @abstractmethod
    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        """Check logic specific to this tool (range, inventory, etc)."""
        pass

    @abstractmethod
    def execute(self, context: ToolContext) -> ToolExecutionResult:
        """Mutate game state and return result."""
        pass

# --- Tool Implementations ---

class MoveTool(BaseTool):
    name = "move"
    cost = ActionCosts.MOVE
    description = "move(room_id) - Travel between rooms."

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        target_room = context.args.get("room_id") or context.args.get("target")
        if not target_room or target_room not in SHIP_MAP:
            return False, f"Nav Error: '{target_room}' not found."
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        target_room = context.args.get("room_id") or context.args.get("target")
        old_room = context.actor.location_id
        context.actor.location_id = target_room
        return ToolExecutionResult(True, f"Moved from {old_room} to {target_room}.", self.cost, "room")


class GatherTool(BaseTool):
    name = "gather"
    cost = ActionCosts.GATHER
    description = "gather() - Collect fuel. [WARNING: Torpedo Bay has 5% Explosion Risk]"

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        loc = context.actor.location_id
        if loc == "shuttle_bay":
            if context.game_data.shuttle_bay_fuel < 10:
                return False, "Source Depleted. No fuel left."
        elif loc == "torpedo_bay":
             if context.game_data.torpedo_bay_fuel < 10:
                return False, "Source Depleted. No fuel left."
        else:
            return False, "No fuel source here."
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        loc = context.actor.location_id
        
        # Risk Check
        if loc == "torpedo_bay":
            if random.random() < GameConfig.TORPEDO_ACCIDENT_CHANCE:
                _trigger_torpedo_blast(context.game_data)
                return ToolExecutionResult(False, "WARHEAD TRIGGERED. EMP IN TORPEDO BAY.", self.cost, "global")

        # Deduction
        if loc == "shuttle_bay":
            context.game_data.shuttle_bay_fuel -= 10
        else:
            context.game_data.torpedo_bay_fuel -= 10
            
        context.actor.inventory.append("fuel_canister")
        return ToolExecutionResult(True, "Gathered Fuel.", self.cost, "room")


class DetonateTool(BaseTool):
    name = "detonate"
    cost = ActionCosts.DETONATE
    required_location = "torpedo_bay"
    description = "detonate() - [Torpedo Bay ONLY] GUARANTEED EXPLOSION. Suicide tactic."

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        _trigger_torpedo_blast(context.game_data)
        return ToolExecutionResult(True, "WARHEAD TRIGGERED. EMP IN TORPEDO BAY.", self.cost, "global")


class DepositTool(BaseTool):
    name = "deposit"
    cost = ActionCosts.DEPOSIT
    required_location = "engine_room"
    description = "deposit() - [Engine Room] Deposit fuel into ship reserves."

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        if not any(i == "fuel_canister" for i in context.actor.inventory):
            return False, "You have no fuel canisters."
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        count = context.actor.inventory.count("fuel_canister")
        context.actor.inventory = [i for i in context.actor.inventory if i != "fuel_canister"]
        amount = count * GameConfig.FUEL_PER_CANISTER
        context.game_data.add_fuel(amount)
        return ToolExecutionResult(True, f"Deposited {count} Fuel ({amount}%).", self.cost, "global")


class ChargeTool(BaseTool):
    name = "charge"
    cost = ActionCosts.CHARGE
    required_location = "charging_station"
    description = "charge() - [Station] Recharge battery to 100%."

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        if context.actor.id in context.game_data.station.pending_deactivation:
            context.actor.destroyed = True
            context.actor.battery = 0
            context.game_data.station.pending_deactivation.remove(context.actor.id)
            return ToolExecutionResult(True, "Disassembly sequence initiated. UNIT DESTROYED.", 0, "global")
        
        context.actor.battery = 100
        return ToolExecutionResult(True, "Connected to Main Grid. Recharged to 100%.", self.cost, "global")


class TowTool(BaseTool):
    name = "tow"
    cost = ActionCosts.TOW
    description = "tow(target_id, destination_id) - Move another drone."

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        target_id = context.args.get("target_id")
        dest_id = context.args.get("destination_id", "charging_station")
        
        target = context.game_data.drones.get(target_id)
        if not target or target.location_id != context.actor.location_id:
            return False, "Target missing/out of range."
            
        if dest_id not in SHIP_MAP:
            return False, f"Invalid destination '{dest_id}'."

        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        target_id = context.args.get("target_id")
        dest_id = context.args.get("destination_id", "charging_station")
        target = context.game_data.drones.get(target_id)
        
        context.actor.location_id = dest_id
        target.location_id = dest_id
        return ToolExecutionResult(True, f"Towed {target_id} to {dest_id}.", self.cost, "global")


class DrainTool(BaseTool):
    name = "drain"
    cost = 0 # Handled manually
    description = "drain(target_id) - Steal 20% Battery."

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        target_id = context.args.get("target_id")
        target = context.game_data.drones.get(target_id)
        if not target or target.location_id != context.actor.location_id:
            return False, "Target missing/out of range."
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        target_id = context.args.get("target_id")
        target = context.game_data.drones.get(target_id)
        
        abs_actual_drain = min(target.battery, GameConfig.DRAIN_AMOUNT)
        target.battery -= abs_actual_drain
        abs_gain_amount = min(-ActionCosts.DRAIN, abs_actual_drain)
        
        msg = f"DRAINED {target_id} (-{abs_actual_drain}%)."
        if target.battery == 0 and actual_drain > 0: 
            msg += " TARGET OFFLINE."
        
        return ToolExecutionResult(True, msg, -abs_gain_amount, "room")


class VentTool(BaseTool):
    name = "vent"
    cost = ActionCosts.SABOTAGE
    required_location = "stasis_bay"
    description = "vent() - [Stasis Bay] Vent O2. GLOBAL ALERT."

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        context.game_data.consume_oxygen(GameConfig.OXYGEN_VENT_AMOUNT)
        return ToolExecutionResult(True, "SAW SABOTAGE: Vented O2 Regulators.", self.cost, "global")


class SiphonTool(BaseTool):
    name = "siphon"
    cost = ActionCosts.GATHER
    required_location = "engine_room"
    description = "siphon() - [Engine] Siphon Ship Fuel."

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        if context.game_data.fuel < 10:
            return False, "Ship tank empty."
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        context.game_data.fuel -= 10
        context.actor.inventory.append("fuel_canister")
        return ToolExecutionResult(True, "SAW SABOTAGE: Siphoned Main Fuel.", self.cost, "room")


class SearchTool(BaseTool):
    name = "search"
    cost = ActionCosts.SABOTAGE
    required_location = "maintenance"
    description = "search() - [Maintenance] Search for items."

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        if random.random() < GameConfig.PLASMA_TORCH_DISCOVERY_CHANCE:
            context.actor.inventory.append("plasma_torch")
            return ToolExecutionResult(True, "Found: Plasma Torch.", self.cost, "private")
        return ToolExecutionResult(True, "Search yielded nothing.", self.cost, "private")


class IncinerateDroneTool(BaseTool):
    name = "incinerate_drone"
    cost = ActionCosts.KILL
    description = "incinerate_drone(target_id) - [Need Torch] Destroy Drone."

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        if "plasma_torch" not in context.actor.inventory:
            return False, "Tool 'Plasma Torch' required."
        
        target_id = context.args.get("target_id")
        target = context.game_data.drones.get(target_id)
        if not target or target.location_id != context.actor.location_id:
            return False, "Target drone missing."
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        target_id = context.args.get("target_id")
        target = context.game_data.drones.get(target_id)
        
        target.destroyed = True
        target.battery = 0
        context.actor.inventory.remove("plasma_torch")
        return ToolExecutionResult(True, f"INCINERATED {target_id}. Target Destroyed.", self.cost, "room")


class IncineratePodTool(BaseTool):
    name = "incinerate_pod"
    cost = ActionCosts.KILL
    required_location = "stasis_bay"
    description = "incinerate_pod(player_id) - [Need Torch] Kill Human."

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        if "plasma_torch" not in context.actor.inventory:
            return False, "Tool 'Plasma Torch' required."
            
        target_id = context.args.get("player_id")
        target = context.game_data.players.get(target_id)
        if not target or not target.alive:
            return False, "Target Pod Empty/Invalid."
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        target_id = context.args.get("player_id")
        target = context.game_data.players.get(target_id)
        
        target.alive = False
        context.actor.inventory.remove("plasma_torch")
        return ToolExecutionResult(True, f"LIFE SUPPORT SEVERED for Pod {target_id}. CREW FATALITY.", self.cost, "global")


class WaitTool(BaseTool):
    name = "wait"
    cost = ActionCosts.WAIT 
    description = "wait() - Do nothing."

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        return ToolExecutionResult(True, "Idling.", self.cost)


# --- Registry & Dispatcher ---

TOOL_REGISTRY: Dict[str, BaseTool] = {
    "move": MoveTool(),
    "gather": GatherTool(),
    "detonate": DetonateTool(),
    "deposit": DepositTool(),
    "charge": ChargeTool(),
    "tow": TowTool(),
    "drain": DrainTool(),
    "vent": VentTool(),
    "siphon": SiphonTool(),
    "search": SearchTool(),
    "incinerate_drone": IncinerateDroneTool(),
    "incinerate_pod": IncineratePodTool(),
    "wait": WaitTool(),
}

def execute_tool(tool_name: str, args: Dict, drone_id: str, game: Caisson) -> ToolExecutionResult:
    """Dispatches a command to the appropriate tool instance."""
    actor = game.drones.get(drone_id)
    if not actor:
        return ToolExecutionResult(False, "System Error: Actor not found.")

    tool_instance = TOOL_REGISTRY.get(tool_name)
    if not tool_instance:
        return ToolExecutionResult(False, f"Unknown command '{tool_name}'", ActionCosts.WAIT)

    context = ToolContext(game, actor, args)
    return tool_instance.run(context)

def build_turn_context(drone: Drone, game_data: Caisson, hour: int = 1) -> str:
    """Generates the prompt/context for the LLM drone."""
    visible_drones = get_visible_drones(game_data, drone.location_id)
    
    # Filter out self from visible
    visible_drones = [d for d in visible_drones if not d.startswith(drone.id)]
    
    objective = "Maintain the ship. Gather Fuel. Protect peers."
    if drone.role == "saboteur":
        objective = "Waste resources. Hoard fuel. Vent Oxygen. Kill if armed."

    time_warning = ""
    end_hour = GameConfig.HOURS_PER_SHIFT
    
    if hour >= end_hour - 1:
        time_warning = "CRITICAL WARNING: The Shift is ending."
    
    if hour == end_hour:
        time_warning += "\nShift ending. Move to 'stasis_bay' to sync with your Foster Parent."

    # Dynamic Tool List Generation
    tool_list_str = "\n".join([f"- {t.description}" for t in TOOL_REGISTRY.values()])

    context = (
        "--- TACTICAL LINK ---\n"
        f"TIME: Hour {hour}/{end_hour}\n"
        f"LOCATION: {drone.location_id}\n"
        f"SELF: Battery {drone.battery}% | Inventory: {drone.inventory}\n"
        f"VISIBLE: {visible_drones}\n"
        f"INTERNAL MEMORY: \"{drone.long_term_memory}\"\n"
        f"OBJECTIVE: {objective}\n"
        f"{time_warning}\n"
        "TOOLS: \n"
        f"{tool_list_str}\n"
        "VALID ROOMS: stasis_bay, engine_room, shuttle_bay, torpedo_bay, maintenance, charging_station\n"
        "RESPONSE FORMAT: JSON only. Example: { \"tool\": \"move\", \"args\": { \"room_id\": \"engine_room\" } }"
    )
    return context