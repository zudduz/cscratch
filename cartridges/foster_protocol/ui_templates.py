from typing import Dict, Any, List
from .models import Drone, Caisson
from .tools import ToolExecutionResult
from .board import GameEndState, GameConfig

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

    # --- TEXT BLOBS ---
    GUIDE_TEXT = """\
**The Foster Protocol: Quick Guide**

**The Goal:** Escape the decaying orbit! Your drone must gather fuel and deposit it in the `engine_room`.
**The Catch:** One (and only one) of the drones is secretly a **Saboteur** trying to stop you.

**Day Phase:** Your drone executes your orders automatically while you're asleep in the stasis pod. Some actions will appear in the logs.
**Night Phase:** Chat with your drone. Ask it what happened and give it instructions for the next day. Coordinate with other players in the aux-comm channel.

**Night Commands (Nanny Channel):**
• `!name <name>` - Give your drone a name.
• `!sleep` - Mark yourself as ready for sleep.
• `!destroy` - Order your drone's destruction at the charging station. The drone won't know until it's too late.
• `!cancel` - Rescind your drone's destruction order.

Send `/cscratch manual` for full instructions.
"""

    MANUAL_TEXT = f"""**The Foster Protocol: Complete Manual**

**CORE MECHANICS**
• **Orbit Decay:** The fuel required for escape velocity will increase every day.
• **Oxygen:** Depletes daily. At 0%, the humans will be put back into stasis (skip night chat). Fewer living humans results in less oxygen used.
• **Battery:** Drones need battery to act. At 0%, they will go offline until they are towed to the `charging_station`.

**ROOMS & RISKS**
• `stasis_bay`: Drones must be here at night or they will be unable to chat.
• `shuttle_bay`: Safe fuel gathering. Contains {GameConfig.CAPACITY_SHUTTLE_BAY} fuel
• `torpedo_bay`: Risky fuel gathering ({GameConfig.TORPEDO_ACCIDENT_PERCENT}% chance of EMP explosion, knocks out all drones in room). Contains {GameConfig.CAPACITY_SHUTTLE_BAY} fuel
• `engine_room`: Fuel can be deposited here (or siphoned).
• `maintenance`: Search here for a `plasma_torch` ({GameConfig.PLASMA_TORCH_DISCOVERY_PERCENT}% chance).
• `charging_station`: Restores battery to 100% at the cost of 1 Ship Fuel. Offline drones will be automatically charged. (Pending `!destroy` orders are executed here).

**DRONE ACTIONS (AI Controlled)**
Your drone decides its actions based on your chat instructions. It can: `move`, `gather`, `deposit`, `charge`, `tow` (offline drones), `drain` (steal battery), `vent` (sabotage O2), `siphon` (steal fuel), `search` (find weapons), `incinerate_drone` / `incinerate_pod` (requires plasma torch). All actions take 1 hour.

**DRONE VISIBILITY**
Many actions are visible to other drones in the same room. Some actions are visible to the mainframe and will be reported to aux-comm channel

**DEATH & DESTRUCTION**
A drone can be incinerated by a peer or disassembled via `!destroy`. A human can also be incinerated by a drone.

**WINNING AND LOSING**
The game is won if at the end of the day cycle the fuel in the engine meets the requirement for escape velocity for that day.
The game is lost if the required fuel for the day is more than the engine is capable of holding.
The game is lost if there are no active drones.
"""

    # --- STARTUP & SETUP ---

    @classmethod
    async def announce_startup(cls, ctx):
        await ctx.send(cls.CHANNEL_AUX, "VENDETTA OS v9.0 ONLINE")
        await ctx.send(cls.CHANNEL_BLACKBOX, "Flight recorder active")

    @classmethod
    async def list_channel_ops(cls, players: List[dict], saboteur_index: int, guild_id: str = None) -> List[dict]:
        """Generates the initial channel creation operations."""
        ops = [
            {"op": "create", "key": cls.CHANNEL_AUX, "name": "aux-comm", "audience": "public"}
        ]
        
        # Only create the black box log channel on the cscratch-dev server
        if guild_id and str(guild_id) == "1455418686931468403":
            ops.append({
                "op": "create", 
                "key": cls.CHANNEL_BLACKBOX, 
                "name": "black-box-logs", 
                "audience": "hidden", 
                "init_msg": "Flight recorder active"
            })
        
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
            f"*{thought}*\n"
            f">> `{result.message}`" 
            f"**[H{hour}] {role_icon} {display_id}** {status_str}\n"
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
    async def report_game_end(cls, ctx, game_end_state):
        if game_end_state == GameEndState.NO_ACTIVE_DRONES:
            await ctx.send(cls.CHANNEL_AUX, "Failure\nNo active drones\nOrbital decay inevitable")
        elif game_end_state == GameEndState.INSUFFICIENT_FUEL_CAPACITY:
            await ctx.send(cls.CHANNEL_AUX, "Failure\nOrbital decay irreversible\nRequired fuel exceeds ship capacity")
        elif game_end_state == GameEndState.BURN_INITIATED:
            await ctx.send(cls.CHANNEL_AUX, "Success!\nSufficient fuel for escape velocity\nInitiating burn...")
        else:
            await ctx.send(cls.CHANNEL_AUX, "Unmapped game end state")

    @classmethod
    async def report_cycle_continuation(cls, ctx, req_tomorrow: int):
        msg = f"Burn Window Missed\nAtmospheric Drag detected.\n**Tomorrow's Fuel Target: {req_tomorrow}%**"
        await ctx.send(cls.CHANNEL_AUX, msg)

    @classmethod
    async def report_stasis_engaged(cls, ctx):
        await ctx.send(cls.CHANNEL_AUX, "Oxygen depleted\nStasis engaged\nThe crew sleeps\nThe drones must continue alone")

    @classmethod
    async def report_saboteur(cls, ctx, saboteur_drone: Drone, foster_name: str):
        final_report = f"\nTraitor: Drone {saboteur_drone.id} (Bonded to <@{foster_name}>)."
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
