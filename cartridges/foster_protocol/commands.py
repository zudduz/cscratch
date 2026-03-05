from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod
import logging

# Type checking imports
from .models import Caisson

class CommandContext:
    def __init__(self, cartridge, game_data: Caisson, ctx, tools, user_id: str, channel_id: str):
        self.cartridge = cartridge
        self.game_data = game_data
        self.ctx = ctx
        self.tools = tools
        self.user_id = user_id
        self.channel_id = channel_id

class BaseCommand(ABC):
    # Source of Truth: Define which channels this command works in
    allowed_contexts: List[str] = [] 

    @abstractmethod
    async def execute(self, args: List[str], context: CommandContext) -> Optional[Dict[str, Any]]:
        pass


# --- NANNY COMMANDS ---

class DestroyDroneCommand(BaseCommand):
    allowed_contexts = ["nanny"]

    async def execute(self, args: List[str], context: CommandContext) -> Optional[Dict[str, Any]]:
        my_drone = next((b for b in context.game_data.drones.values() if b.foster_id == context.user_id), None)
        
        if not my_drone:
            await context.ctx.reply("No drone assigned to this channel.")
            return None
            
        target_id = my_drone.id
        
        if target_id not in context.game_data.station.pending_deactivation:
            context.game_data.station.pending_deactivation.append(target_id)
            await context.ctx.reply(f"**DESTRUCTION AUTHORIZED.**\nDrone {target_id} will be destroyed upon next Charging Cycle.")
            return {"station": context.game_data.station.model_dump()}
        else:
            await context.ctx.reply(f"Drone {target_id} is already scheduled for destruction.")
            return None

class AbortCommand(BaseCommand):
    allowed_contexts = ["nanny"]

    async def execute(self, args: List[str], context: CommandContext) -> Optional[Dict[str, Any]]:
        my_drone = next((b for b in context.game_data.drones.values() if b.foster_id == context.user_id), None)
        
        if not my_drone:
            return None
            
        target_id = my_drone.id
        
        if target_id in context.game_data.station.pending_deactivation:
            context.game_data.station.pending_deactivation.remove(target_id)
            await context.ctx.reply(f"**ORDER RESCINDED.** Drone {target_id} is safe.")
            return {"station": context.game_data.station.model_dump()}
        return None

class NameDroneCommand(BaseCommand):
    allowed_contexts = ["nanny"]

    async def execute(self, args: List[str], context: CommandContext) -> Optional[Dict[str, Any]]:
        my_drone = next((b for b in context.game_data.drones.values() if b.foster_id == context.user_id), None)
        if not my_drone: return None
        
        if len(args) < 1:
            await context.ctx.reply("USAGE: !name <new_name>")
            return None
            
        # Rejoin arguments to allow spaces in names
        new_name = " ".join(args)[:20]
        my_drone.name = new_name
        
        await context.ctx.reply(f"Identity Updated. Hello, **{new_name}**. (ID: {my_drone.id})")
        return {f"drones.{my_drone.id}.name": new_name}

class SleepCommand(BaseCommand):
    allowed_contexts = ["nanny"]

    async def execute(self, args: List[str], context: CommandContext) -> Optional[Dict[str, Any]]:
        user_id = context.user_id
        if user_id in context.game_data.players:
            context.game_data.players[user_id].requested_sleep = True
            
            await context.ctx.reply(f"Sleep request logged")
            if context.game_data.is_ready_for_day:
                await context.ctx.send("aux-comm", "The crew is asleep\nBeginning day cycle")
                
                context.game_data.phase = "day"
                for p in context.game_data.players.values():
                    p.requested_sleep = False
                
                context.ctx.schedule(context.cartridge.execute_day_simulation(context.game_data, context.ctx, context.tools))
                return {"metadata": context.game_data.model_dump()}
            
            return {f"players.{user_id}.requested_sleep": True}
        return None

REGISTRY = {
    "!destroy": DestroyDroneCommand(),
    "!cancel": AbortCommand(),
    "!name": NameDroneCommand(),
    "!sleep": SleepCommand()
}

async def dispatch(command_name: str, args: List[str], context: CommandContext) -> Optional[Dict[str, Any]]:
    cmd = REGISTRY.get(command_name)
    if cmd:
        return await cmd.execute(args, context)
    return None

async def handle_command(user_input: str, context: CommandContext) -> Optional[Dict[str, Any]]:
    parts = user_input.strip().split()
    cmd_name = parts[0].lower()
    args = parts[1:]
    
    # Recover interface channels from the context trigger data
    interface_channels = context.ctx.trigger_data.get('interface', {}).get('channels', {})
    
    # Determine Context Type
    channel = None
    if context.channel_id == interface_channels.get('aux-comm'):
        channel = "aux"
    elif context.channel_id == interface_channels.get(f"nanny_{context.user_id}"):
        channel = "nanny"
    
    # Dispatch Logic
    cmd_instance = REGISTRY.get(cmd_name)
    
    if cmd_instance:
        if channel in cmd_instance.allowed_contexts:
            return await cmd_instance.execute(args, context)

    # Error Handling / Fallback
    if channel in ["aux", "nanny"]:
        available_commands = [cmd for cmd, instance in REGISTRY.items() if channel in instance.allowed_contexts]
        available_str = ", ".join(available_commands)
        await context.ctx.reply(f"Unknown Command: '{cmd_name}'\nAvailable: {available_str}")
        return None
        
    return None