from typing import Dict, Any, List
from .models import Drone, Caisson
from .tools import ToolExecutionResult

class FosterPresenter:
    """
    The View Layer for The Foster Protocol.
    Stateless class acting as a namespace for UI formatting and Discord interactions.
    """

    # --- CONSTANTS ---
    ICON_SABOTEUR = "[SABOTEUR]"
    ICON_LOYAL = "[LOYAL]"
    
    CHANNEL_AUX = "aux-comm"
    CHANNEL_BLACKBOX = "black-box"

    # --- STARTUP & SETUP ---

    @classmethod
    async def announce_startup(cls, ctx):
        await ctx.send(cls.CHANNEL_AUX, "VENDETTA OS v9.0 ONLINE")
        await ctx.send(cls.CHANNEL_BLACKBOX, "Flight recorder active")

    @classmethod
    async def list_channel_ops(cls, players: List[dict], saboteur_index: int) -> List[dict]:
        """Generates the initial channel creation operations."""
        ops = [
            {"op": "create", "key": cls.CHANNEL_AUX, "name": "aux-comm", "audience": "public"},
            {"op": "create", "key": cls.CHANNEL_BLACKBOX, "name": "black-box-logs", "audience": "hidden", "init_msg": "Flight recorder active"}
        ]
        
        for i, p_data in enumerate(players):
            u_id = p_data['id']
            u_name = p_data['name']
            ops.append({
                "op": "create", 
                "key": f"nanny_{u_id}", 
                "name": f"nanny-port-{u_name}", 
                "audience": "private", 
                "user_id": u_id
            })
            
        return ops

    # --- DAY LOOP REPORTING ---

    @classmethod
    async def report_blackbox_event(cls, ctx, hour: int, drone: Drone, result: ToolExecutionResult, thought: str):
        """Formats the raw event data into the stylized Black Box log."""
        role_icon = cls.ICON_SABOTEUR if drone.role == "saboteur" else cls.ICON_LOYAL
        display_id = f"{drone.name} ({drone.id})" if drone.name else drone.id
        inv_str = str(drone.inventory) if drone.inventory else "[]"
        status_str = f"[Bat:{drone.battery}% | Loc:{drone.location_id} | Inv:{inv_str}]"
        
        msg = (
            f"**[H{hour}] {role_icon} {display_id}** {status_str}\n"
            f"*{thought}*\n"
            f">> `{result.message}`" 
        )
        await ctx.send(cls.CHANNEL_BLACKBOX, msg)

    @classmethod
    async def report_public_event(cls, ctx, hour: int, message: str):
        """Broadcasts a global event to the main comms."""
        public_msg = f"[Hour {hour}] {message}"
        await ctx.send(cls.CHANNEL_AUX, public_msg)
        return public_msg

    @classmethod
    async def report_hourly_status_nominal(cls, ctx, hour: int):
        msg = f"[Hour {hour}] Ship systems nominal."
        await ctx.send(cls.CHANNEL_AUX, msg)
        return msg

    @classmethod
    async def report_drone_eulogy(cls, ctx, drone: Drone, last_words: str):
        display_name = drone.name if drone.name else drone.id
        role_reveal = f"Analysis: Drone was [{drone.role.upper()}]."
        msg = f"Decommission log - {display_name}:\n{role_reveal}\n\"{last_words}\""
        await ctx.send(cls.CHANNEL_AUX, msg)

    # --- END OF DAY / CYCLE ---

    @classmethod
    async def report_cycle_status(cls, ctx, cycle: int, oxygen: int, oxygen_drop: int, fuel: int, req_today: int):
        report = (
            f"**Cycle {cycle} report**\n"
            f"Oxygen: {oxygen}% (-{oxygen_drop}%/day)\n"
            f"Fuel status: {fuel}% / {req_today}% required"
        )
        await ctx.send(cls.CHANNEL_AUX, report)
        return report

    @classmethod
    async def report_victory(cls, ctx):
        await ctx.send(cls.CHANNEL_AUX, "Success!\nSufficient fuel for escape velocity\nInitiating burn...")

    @classmethod
    async def report_failure_orbital_decay(cls, ctx):
        await ctx.send(cls.CHANNEL_AUX, "Failure\nOrbital decay irreversible\nRequired fuel exceeds ship capacity")

    @classmethod
    async def report_cycle_continuation(cls, ctx, req_tomorrow: int):
        msg = f"Burn Window Missed\nAtmospheric Drag detected.\n**Tomorrow's Fuel Target: {req_tomorrow}%**"
        await ctx.send(cls.CHANNEL_AUX, msg)

    @classmethod
    async def report_stasis_engaged(cls, ctx):
        await ctx.send(cls.CHANNEL_AUX, "Oxygen depleted\nStasis engaged\nThe crew sleeps\nThe drones must continue alone")

    @classmethod
    async def report_mission_summary(cls, ctx, victory: bool, fail_reason: str, saboteur_drone: Drone, foster_name: str):
        if victory:
            final_report = f"Mission: Success"
        else:
            final_report = f"Mission: Failure\nReason: {fail_reason}"
        
        final_report += f"\nTraitor: Drone {saboteur_drone.id} (Bonded to <@{foster_name}>)."
        await ctx.send(cls.CHANNEL_AUX, final_report)

    # --- CHAT & INTERACTION ---

    @classmethod
    async def send_private_message(cls, ctx, user_id: str, text: str):
        key = f"nanny_{user_id}"
        await ctx.send(key, text)

    @classmethod
    async def reply_no_drone_present(cls, ctx):
        await ctx.reply("Message not delivered\nNo drone present")

    @classmethod
    async def reply_day_phase_active(cls, ctx):
        await ctx.reply("Day cycle in progress\nYou are sleeping now\nPretend to snore or something")

    @classmethod
    async def send_system_error(cls, ctx, error_msg: str):
        await ctx.send(cls.CHANNEL_AUX, f"SYSTEM ERROR! Error message: {error_msg}")