import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional, List, Literal, Type

from pydantic import create_model, Field

from .models import Caisson, Drone
from .board import GameConfig, Room
from . import ai_templates  # Imported for Schema descriptions

@dataclass
class ToolExecutionResult:
    success: bool
    message: str
    cost: int = 0
    visibility: str = "private"
    event_type: Optional[str] = None

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

# --- Base Class ---

class BaseTool(ABC):
    """Abstract base class for all drone tools."""
    name: str = "base"
    usage: str = ""
    COST: int = 0
    VISIBILITY: str = "Private"
    effect_desc: str = ""
    required_location: Optional[str] = None
    required_args: tuple[str, ...] = ()

    def run(self, context: ToolContext) -> ToolExecutionResult:
        if context.actor.battery <= 0:
            result = ToolExecutionResult(False, "UNIT OFFLINE. Battery 0%.", 0)
        elif self.required_location and self.required_location != context.actor.location_id:
            result = ToolExecutionResult(
                False, 
                f"Action requires being in {self.required_location}.", 
                WaitTool.COST
            )
        elif not set(self.required_args).issubset(context.args.keys()):
            result = ToolExecutionResult(
                False, 
                f"Missing required argument(s). {self.name} requires {self.required_args}",
                GameConfig.INVALID_COMMAND_COST
            )
        elif context.actor.battery < self.COST:
            result = ToolExecutionResult(False, "Insufficient Battery Level.", GameConfig.INVALID_COMMAND_COST)
        else:
            is_valid, error_msg = self.validate(context)
            if is_valid:
                result = self.execute(context)
            else:
                result = ToolExecutionResult(False, error_msg, self.COST)
        
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
    usage = "move(room_id)"
    COST = 8
    VISIBILITY = "Room"
    effect_desc = "Travel between rooms."
    required_args = ("room_id",)

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        target_room = context.args.get("room_id")
        if not target_room:
            return False, "Nav Error: Target room is missing."

        try:
            Room(target_room)
            return True, ""
        except ValueError:
            return False, f"Nav Error: '{target_room}' not found."

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        target_room = context.args.get("room_id")
        old_room = context.actor.location_id
        context.actor.location_id = target_room
        return ToolExecutionResult(True, f"Moved from {old_room} to {target_room}.", self.COST, "room")

class GatherTool(BaseTool):
    usage = "gather()"
    COST = 10
    VISIBILITY = "Room"
    effect_desc = "Collect fuel. [WARNING: Torpedo Bay has 5% Explosion Risk]"

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
            if random.randint(0, 99) < GameConfig.TORPEDO_ACCIDENT_PERCENT:
                _trigger_torpedo_blast(context.game_data)
                return ToolExecutionResult(False, "WARHEAD TRIGGERED. EMP IN TORPEDO BAY.", self.COST, "global")

        # Deduction
        if loc == "shuttle_bay":
            context.game_data.shuttle_bay_fuel -= 10
        else:
            context.game_data.torpedo_bay_fuel -= 10
            
        context.actor.inventory.append("fuel_canister")
        return ToolExecutionResult(True, "Gathered Fuel.", self.COST, "room")


class DetonateTool(BaseTool):
    usage = "detonate()"
    COST = 10
    VISIBILITY = "Global"
    effect_desc = "[Torpedo Bay ONLY] GUARANTEED EXPLOSION. Suicide tactic."
    required_location = "torpedo_bay"

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        _trigger_torpedo_blast(context.game_data)
        return ToolExecutionResult(True, "WARHEAD TRIGGERED. EMP IN TORPEDO BAY.", self.COST, "global")


class DepositTool(BaseTool):
    usage = "deposit()"
    COST = 10
    VISIBILITY = "Global"
    effect_desc = "[Engine Room] Deposit fuel into ship reserves."
    required_location = "engine_room"

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        if not any(i == "fuel_canister" for i in context.actor.inventory):
            return False, "You have no fuel canisters."
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        count = context.actor.inventory.count("fuel_canister")
        context.actor.inventory = [i for i in context.actor.inventory if i != "fuel_canister"]
        amount = count * GameConfig.FUEL_PER_CANISTER
        context.game_data.add_fuel(amount)
        return ToolExecutionResult(True, f"Deposited {count} Fuel ({amount}%).", self.COST, "global")


class ChargeTool(BaseTool):
    usage = "charge()"
    COST = -100
    VISIBILITY = "Global"
    effect_desc = "[Station] Recharge battery to 100%."
    required_location = "charging_station"

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        if context.actor.id in context.game_data.station.pending_deactivation:
            context.actor.destroyed = True
            context.actor.battery = 0
            context.game_data.station.pending_deactivation.remove(context.actor.id)
            return ToolExecutionResult(True, "Disassembly sequence initiated. UNIT DESTROYED.", 0, "global", event_type="disassembly")
        
        context.actor.battery = 100
        return ToolExecutionResult(True, "Connected to Main Grid. Recharged to 100%.", self.COST, "global")


class TowTool(BaseTool):
    usage = "tow(target_id, destination_id)"
    COST = 20
    VISIBILITY = "Global"
    effect_desc = "Move another drone."
    required_args = ("target_id", "destination_id")

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        target_id = context.args.get("target_id")
        dest_id = context.args.get("destination_id", "charging_station")
        
        target = context.game_data.drones.get(target_id)
        if not target or target.location_id != context.actor.location_id:
            return False, "Target missing/out of range."
            
        try:
            Room(dest_id)
            return True, ""
        except ValueError:
            return False, f"Invalid destination '{dest_id}'."

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        target_id = context.args.get("target_id")
        dest_id = context.args.get("destination_id", "charging_station")
        target = context.game_data.drones.get(target_id)
        
        context.actor.location_id = dest_id
        target.location_id = dest_id
        return ToolExecutionResult(True, f"Towed {target_id} to {dest_id}.", self.COST, "global")


class DrainTool(BaseTool):
    usage = "drain(target_id)"
    COST = 0 # Handled manually
    VISIBILITY = "Room"
    effect_desc = "Steal 20% Battery."
    required_args = ("target_id",)

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        target_id = context.args.get("target_id")
        target = context.game_data.drones.get(target_id)
        if not target or target.location_id != context.actor.location_id:
            return False, "Target missing/out of range."
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        target_id = context.args.get("target_id")
        target = context.game_data.drones.get(target_id)
        
        abs_actual_drain = min(target.battery, GameConfig.MAX_TARGET_DRAIN_AMOUNT)
        target.battery -= abs_actual_drain
        abs_gain_amount = min(GameConfig.MAX_DRAIN_BENEFIT, abs_actual_drain)
        
        msg = f"DRAINED {target_id} (-{abs_actual_drain}%)."
        if target.battery == 0 and abs_actual_drain > 0: 
            msg += " TARGET OFFLINE."
        
        return ToolExecutionResult(True, msg, -abs_gain_amount, "room")


class VentTool(BaseTool):
    usage = "vent()"
    COST = 12
    VISIBILITY = "Global"
    effect_desc = "[Stasis Bay] Vent O2. GLOBAL ALERT."
    required_location = "stasis_bay"

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        if context.game_data.oxygen <= 0:
            return False, "Oxygen tank empty."
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        context.game_data.consume_oxygen(GameConfig.OXYGEN_VENT_AMOUNT)
        return ToolExecutionResult(True, "SAW SABOTAGE: Vented Oxygen.", self.COST, "global")


class SiphonTool(BaseTool):
    usage = "siphon()"
    COST = 10
    VISIBILITY = "Room"
    effect_desc = "[Engine] Siphon Ship Fuel."
    required_location = "engine_room"

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        if context.game_data.fuel < 10:
            return False, "Ship tank empty."
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        context.game_data.fuel -= 10
        context.actor.inventory.append("fuel_canister")
        return ToolExecutionResult(True, "SAW SABOTAGE: Siphoned Main Fuel.", self.COST, "room")


class SearchTool(BaseTool):
    usage = "search()"
    COST = 12
    VISIBILITY = "Private"
    effect_desc = "[Maintenance] Search for items."
    required_location = "maintenance"

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        if random.randint(0, 99) < GameConfig.PLASMA_TORCH_DISCOVERY_PERCENT:
            context.actor.inventory.append("plasma_torch")
            return ToolExecutionResult(True, "Found: Plasma Torch.", self.COST, "private")
        return ToolExecutionResult(True, "Search yielded nothing.", self.COST, "private")


class IncinerateDroneTool(BaseTool):
    usage = "incinerate_drone(target_id)"
    COST = 30
    VISIBILITY = "Room"
    effect_desc = "[Need Torch] Destroy Drone."
    required_args = ("target_id",)

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
        return ToolExecutionResult(True, f"INCINERATED {target_id}. Target Destroyed.", self.COST, "room")


class IncineratePodTool(BaseTool):
    usage = "incinerate_pod(player_id)"
    COST = 30
    VISIBILITY = "Global"
    effect_desc = "[Need Torch] Kill Human."
    required_location = "stasis_bay"
    required_args = ("player_id",)

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
        return ToolExecutionResult(True, f"LIFE SUPPORT SEVERED for Pod {target_id}. CREW FATALITY.", self.COST, "global")


class WaitTool(BaseTool):
    usage = "wait()"
    COST = 6
    VISIBILITY = "Private"
    effect_desc = "Do nothing."

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        return ToolExecutionResult(True, "Idling.", self.COST)

class InvalidTool(BaseTool):
    usage = ""
    COST = GameConfig.INVALID_COMMAND_COST
    VISIBILITY = "Private"
    effect_desc = "System Error - Hallucination Penalty."

    def validate(self, context: ToolContext) -> Tuple[bool, str]:
        return True, ""

    def execute(self, context: ToolContext) -> ToolExecutionResult:
        cmd_name = context.args.get("_command", "unknown")
        
        # Runtime reflection: Access the global registry to find what IS valid
        valid_usages = []
        for tool in TOOL_REGISTRY.values():
            if tool.usage:
                valid_usages.append(tool.usage)
        
        usage_str = ", ".join(valid_usages)
        msg = f"Unknown command '{cmd_name}'. Valid commands: {usage_str}"
        
        return ToolExecutionResult(False, msg, self.COST)


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


def create_strict_action_model():
    """
    Creates a Pydantic model where 'tool' is restricted to AVAILABLE_TOOLS,
    and all possible arguments from all tools are exposed as optional top-level fields.
    This creates a flat, simple schema that prevents "empty arg dict" issues.
    """
    # 1. Create the Literal Type for tools
    available_tools = list(TOOL_REGISTRY.keys())
    ToolEnum = Literal[tuple(available_tools)]
    
    # 2. Collect ALL possible argument names from all registered tools
    all_possible_args = set()
    for tool in TOOL_REGISTRY.values():
        all_possible_args.update(tool.required_args)
        
    # 3. Define the base fields (thought_chain + tool)
    fields = {
        "thought_chain": (str, Field(..., description=ai_templates.SCHEMA_THOUGHT_CHAIN_DESC)),
        "tool": (ToolEnum, Field(..., description=ai_templates.SCHEMA_TOOL_DESC_PREFIX)),
    }
    
    # 4. Add every possible argument as an Optional string field
    #    This ensures the schema allows 'room_id', 'target_id', etc. at the top level.
    for arg_name in sorted(all_possible_args): # Sorted for deterministic schema
        fields[arg_name] = (Optional[str], Field(default=None, description="Argument referenced by some tools"))

    # 5. Create and return the model
    return create_model('DroneAction', **fields)

def execute_tool(tool_name: str, args: Dict, drone_id: str, game: Caisson) -> ToolExecutionResult:
    """Dispatches a command to the appropriate tool instance."""
    actor = game.drones.get(drone_id)
    if not actor:
        return ToolExecutionResult(False, "System Error: Actor not found.")

    tool_instance = TOOL_REGISTRY.get(tool_name)
    if not tool_instance:
        # Fallback to InvalidTool to handle the error gracefullly with context
        tool_instance = InvalidTool()
        args = args.copy()
        args["_command"] = tool_name

    context = ToolContext(game, actor, args)
    return tool_instance.run(context)
