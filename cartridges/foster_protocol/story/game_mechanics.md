# THE FOSTER PROTOCOL: Game Mechanics & Architecture

## 1. The Core Loop (Turn Structure)
The game operates on a **5-Hour Orbital Cycle** (The Work Shift). 
The engine processes the "Day" instantly, simulating 5 tactical hours.

| Phase | Duration | Activity |
| :--- | :--- | :--- |
| **Day (Separation)** | Instant | Orphans detach. Engine simulates 5 tactical turns using `tools.py`. |
| **Night (The Dock)** | Configurable | Orphans return to Nanny Ports to report their logs. Battery must be > 0% and Loc == Cryo Bay. |

## 2. Resource Meters
* **Oxygen:** Lose Condition at 0%. Drops 25% daily. Saboteurs can `vent` to speed this up.
* **Fuel:** Win Condition at 100%. Gathered in Bays, Deposited in Engine.
* **Battery:** (Per Bot) 10% base decay per hour. Heavy actions cost more.
    * 0% = Offline (Cannot move/speak).
    * `charge()` resets to 100%.

## 3. The Map
1. **Cryo Bay:** Nanny Ports (Chat Enabled). Safe Zone.
2. **Maintenance:** Searchable for Items (Plasma Torch).
3. **Torpedo Bay:** Fuel Source (High Yield).
4. **Shuttle Bay:** Fuel Source (Low Yield).
5. **Engine Room:** Deposit Point. Saboteurs can `siphon` here.
6. **Charging Station:** The Critical Node. 
    * `charge()` sets battery to 100%.
    * **The Trap:** If a player has issued `!disassemble` in Mainframe, any bot entering here is DESTROYED.

## 4. Agent Tool Definitions
* `move(room_id)`: Cost 12.
* `gather()`: Cost 15. Get Fuel.
* `deposit()`: Cost 15. Score Fuel.
* `charge()`: Cost 0. Set Bat=100.
* `tow(target_id)`: Cost 20. Drag disabled bot to Charging Station.
* `jolt(target_id)`: Cost 25. Attack (-15 Bat).
* `vent()`: Cost 20. Sabotage (-5 Oxy).
* `siphon()`: Cost 20. Steal (-10 Fuel).
* `search()`: Cost 20. Find Plasma Torch.
* `incinerate(target_id)`: Cost 50. KILL (Requires Torch).
