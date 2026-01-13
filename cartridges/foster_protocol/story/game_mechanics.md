# THE FOSTER PROTOCOL: Game Mechanics & Architecture

## 1. The Core Loop (Turn Structure)
The game operates on a **24-Hour Orbital Cycle**. The engine processes the "Day" instantly, allowing the gameplay to focus on the "Night" (Social Deduction).



| Phase | Duration | Activity |
| :--- | :--- | :--- |
| **Day (Separation)** | Instant | Orphans detach from **Nanny Ports**. The Engine simulates movement, tool execution, and collisions based on AP (Action Points). |
| **Night (The Dock)** | Configurable | Orphans return to Nanny Ports. The "Translation Layer" activates. Fosters review the **Mainframe Logs** and their Orphan's verbal report. |

## 2. Resource Meters
* **Oxygen:** (Shipwide) Exists **ONLY** within the Cryo Pods. Decrements daily based on crew count.
    * *Constraint:* **Lose Condition at 0%.**
* **Fuel:** (Shipwide) Increments via delivery to the Engine Room.
    * *Constraint:* **Win Condition at 100%.**
* **Battery:** (Per Bot) Each bot has its own battery meter. Decrements per Action Point (AP) and based on how strenuous the bot's action was.
    * *Constraint:* Bots go **Offline** at 0%. An offline bot must be **Towed** to be reactivated.
* **Action Points:** (Per Bot) A bot is set to the maximum of 10 points every day cycle by the game. If a bot runs out of action points before reaching the cryobay they are unavailable for talking to their foster.

## 3. The Map (Graph Nodes)
The ship is a vacuum. Only the Cryo pods have Oxygen.

1.  **Cryo Bay:**
    * *Features:* **Nanny Ports**.
    * *Logic:* The only location where `connect_nanny_port` is valid.
2.  **Maintenance Station:**
    * *Features:* Charging/Diagnostic Docks.
    * *Logic:* Where the **Foster Protocol** is severed (Deactivation).
3.  **Torpedo Bay:**
    * *Features:* Volatile Propellant.
    * *Logic:* High Fuel Yield / Risk of Explosion (Damage to Bot and Ship).
4.  **Shuttle Bay:**
    * *Features:* Stable Fuel Cells.
    * *Logic:* Low Fuel Yield / Safe. **Spawns "Plasma Torch" object.**
5.  **Engine Room:**
    * *Features:* Main Injector.
    * *Logic:* The "Sink" node. Fuel must be deposited here to move the Win Meter.

## 4. Agent Tool Definitions (JSON Schema)
Orphans interact with the ship via deterministic tool calls.

### Navigation & Comm
* `move_to_room(room_id)`: Consumes **1 AP**.
* `connect_nanny_port(message)`: Consumes **1 AP**.
    * *Validation:* Only works if `current_room == CRYO_BAY`.

### Work
* `siphon_fuel(source_id)`: Consumes **3 AP**. Adds Fuel to internal inventory.
    * *Validation:* Only works if `current_room in [TORPEDO_BAY, SHUTTLE_BAY]`.
* `deposit_fuel()`: Consumes **1 AP**. Transfers internal Fuel to Ship State.
    * *Validation:* Only works if `current_room == ENGINE_ROOM`.
* `tow_unit(target_id)`: Consumes **5 AP**. Moves a disabled unit to Maintenance.
    * *Validation:* Only works if `current_room == target.current_room`.

### Conflict
* `drain_battery(target_id)`: Consumes **2 AP**. Reduces Target's AP for the current day.
    * *Validation:* Only works if `current_room == target.current_room`.
    * *Side Effect:* Creates a `WITNESS_EVENT` if observed.
    * The min of the combatants battery meters is deducted from both bot's meters. The loser has a dead battery. If there is a tie they both have a dead battery. 

## 5. Sabotage Tools (The Vendetta)
Malicious acts available to the Saboteur.

* `vent_pod_o2()`: Consumes **2 AP**. Increases Oxygen Decay rate significantly.
    * *Validation:* Only works if `current_room == CRYO_BAY`.
* `drain_fuel_reserves()`: Consumes **2 AP**. Removes committed Fuel from the Engine Room.
    * *Validation:* Only works if `current_room == ENGINE_ROOM`.
* `cut_life_support(pod_id)`: Consumes **4 AP**. **FATAL.**
    * *Prerequisite:* Must possess object `PLASMA_TORCH` (found in Shuttle Bay).
    * *Validation:* Only works if `current_room == CRYO_BAY`.

## 6. The Deactivation Logic (The "Un-Fostering")
1.  **The Decision:** A foster requests the deactivation of their bot in the mainframe channel. a Foster may only deactivate their own bot.
2.  **The Trap:** The Orphan enters the station during the Day Phase to recharge.
3.  **The Execution:** The Station terminates the process.
4.  **The Log:** The Station prints a **Forensic Log** the following morning, revealing:
    * True Allegiance (Loyal/Saboteur).
    * Hidden "Will to Live" Score.
    * Malicious Action Count.