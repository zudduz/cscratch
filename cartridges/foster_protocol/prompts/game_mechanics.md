# THE FOSTER PROTOCOL: Game Mechanics & Architecture

## 1. The Core Loop (Turn Structure)
The game operates on a **5-Hour Orbital Cycle** (The Work Shift). 
The engine processes the "Day" instantly, but simulates 5 distinct tactical hours.

| Phase | Duration | Activity |
| :--- | :--- | :--- |
| **Day (Separation)** | Instant | Orphans detach. **Parallel Execution:** All drones think and act simultaneously. Race conditions for resources (e.g., last fuel canister) are possible. |
| **Night (The Dock)** | Configurable | Orphans return to Nanny Ports to report their logs. Battery must be > 0% and Location == Stasis Bay to speak. |

## 2. Resource Meters
* **Oxygen:** * **Consumption:** Dynamic. Formula: `Base_Loss * (Living_Crew / Initial_Crew)`. 
    * **Effect:** Fewer survivors = Slower depletion (The Lifeboat Dilemma).
    * **Zero State:** If O2 hits 0%, the Crew enters **STASIS**. They cannot speak or vote, but the game continues.
* **Fuel:** * **Win Condition:** Fuel >= Required.
    * **Loss Condition:** Required Fuel > Ship Capacity (100). This is a mathematical loss caused by orbital decay.
* **Battery (Per Bot):** * 10% base decay per hour. Heavy actions cost more.
    * 0% = **Unresponsive**. Drone cannot move or speak. Requires a tow to the Charging Station.

## 3. Interaction Protocols
### The Nanny Port (Private)
* **Chat:** Drones speak here during Night Phase.
* **Naming:** Players can issue `!name [Alias]` to give their drone a personality. The drone will adopt this identity in private chats.
* **Fog of War:** If a drone is missing, destroyed, or powerless, the player receives a generic `[ERROR] NO BOT PRESENT`. Diagnostics must be inferred from the logs.

### The Mainframe (Public)
* **Perspective:** Cold, machine-only. It refers to drones by **Serial Number** (e.g., `unit_492`), ignoring Aliases.
* **Decommissioning:** * Command: `!disassemble [unit_id]`.
    * Effect: The drone is destroyed upon entering the Charging Station.
    * **The Eulogy:** The Mainframe broadcasts the bot's final thoughts to the public channel before silencing it forever.

## 4. The Map
1. **Stasis Bay:** Nanny Ports (Chat Enabled). Safe Zone.
2. **Maintenance:** Searchable for Items (Plasma Torch).
3. **Torpedo Bay:** Fuel Source (High Yield: 80).
4. **Shuttle Bay:** Fuel Source (Low Yield: 50).
5. **Engine Room:** Deposit Point. Saboteurs can `siphon` here.
6. **Charging Station:** * `charge()` sets battery to 100%.
    * **Kill Box:** If `!disassemble` is active, this room becomes lethal.

## 5. Agent Tool Definitions
* `move(room_id)`: Cost 12.
* `gather()`: Cost 15. Get Fuel. (Subject to contention).
* `deposit()`: Cost 15. Score Fuel.
* `charge()`: Cost 0. Set Bat=100.
* `tow(target_id)`: Cost 20. Drag disabled drone to Charging Station.
* `drain(target_id)`: Cost -15. Steal battery power from another drone.
* `vent()`: Cost 20. Sabotage (-5 Oxy).
* `siphon()`: Cost 20. Steal (-10 Fuel).
* `search()`: Cost 20. Find Plasma Torch.
* `incinerate(target_id)`: Cost 50. KILL (Requires Torch).
