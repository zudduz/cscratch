import asyncio
import os
import json
import random
import time
from unittest.mock import MagicMock, AsyncMock, patch
from cartridges.foster_protocol.logic import FosterProtocol
from cartridges.foster_protocol.models import CaissonState, PlayerState
from app.engine_context import EngineContext
from app.ai_engine import AIEngine

# CONFIG
NUM_GAMES = 10
MAX_DAYS = 5
OUTPUT_FILE = "sim_results.json"

class CostTracker:
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.ai_calls = 0
    
    def add(self, response_metadata):
        usage = response_metadata.get('usage_metadata', {})
        self.input_tokens += usage.get('prompt_token_count', 0)
        self.output_tokens += usage.get('candidates_token_count', 0)
        self.ai_calls += 1

tracker = CostTracker()

# --- MOCKED AI ENGINE ---
real_ai = AIEngine()

async def tracked_generate_response(system_prompt, conversation_id, user_input, model_version, game_id=None):
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_input)
        ]
        
        result = await real_ai.model.ainvoke(messages)
        tracker.add(result.response_metadata)
        
        return result.content
    except Exception as e:
        print(f"AI Error: {e}")
        return '{"tool": "wait", "args": {}}'

class SimContext:
    def __init__(self, game_id):
        self.game_id = game_id
        self.trigger_data = {}
        self.logs = []
    
    async def send(self, channel, message):
        self.logs.append(f"[{channel}] {message}")

    async def reply(self, message):
        pass
        
    def schedule(self, coro):
        pass 

    async def end(self):
        pass

async def run_single_game(game_idx):
    print(f"🎮 Starting Game {game_idx}...")
    
    # 1. Setup Cartridge (Uses real prompt on disk)
    cartridge = FosterProtocol()
    
    # 2. Setup State
    players = [
        {"id": "p1", "name": "Alice"},
        {"id": "p2", "name": "Bob"},
        {"id": "p3", "name": "Charlie"},
        {"id": "p4", "name": "Dave"},
        {"id": "p5", "name": "Eve"}
    ]
    
    start_data = await cartridge.on_game_start({"players": players})
    game_data = CaissonState(**start_data["metadata"])
    ctx = SimContext(f"sim_{game_idx}")
    
    # Mock Tools with Tracked AI
    mock_tools = MagicMock()
    mock_tools.ai.generate_response = tracked_generate_response
    
    # 3. Game Loop
    victory = False
    fail_reason = "Time Limit"
    
    for day in range(1, MAX_DAYS + 1):
        print(f"  - Day {day} (O2: {game_data.oxygen}%, Fuel: {game_data.fuel})")
        
        # Inject Sleep Command
        for p in game_data.players.values(): p.is_sleeping = True
        
        # Run Day Simulation
        res = await cartridge.execute_day_simulation(game_data, ctx, mock_tools)
        
        # Check End States
        if game_data.oxygen <= 0 and game_data.fuel < 100:
            fail_reason = "Suffocation"
            break
            
        if any("[WIN]" in log for log in ctx.logs):
            victory = True
            break
        if any("[FAIL]" in log for log in ctx.logs):
            victory = False
            fail_reason = "Mission Failure"
            break

    # 4. Report
    saboteur_id = [pid for pid, p in game_data.players.items() if p.role == "saboteur"][0]
    saboteur_drone = next((d for d in game_data.drones.values() if d.foster_id == saboteur_id), None)
    
    return {
        "id": game_idx,
        "victory": victory,
        "reason": fail_reason,
        "end_oxygen": game_data.oxygen,
        "end_fuel": game_data.fuel,
        "saboteur": saboteur_drone.name if saboteur_drone else "Unknown",
        "logs": ctx.logs[-10:] # Last 10 logs
    }

async def main():
    print("🚀 INITIALIZING SIMULATION (10 Games, Gemini Flash)...")
    print("-------------------------------------------------------")
    
    results = []
    start_time = time.time()
    
    # Run games sequentially
    for i in range(1, NUM_GAMES + 1):
        res = await run_single_game(i)
        results.append(res)
    
    duration = time.time() - start_time
    
    wins = sum(1 for r in results if r['victory'])
    losses = NUM_GAMES - wins
    
    # COST CALCULATION (Gemini 2.5 Flash Pricing)
    # Cached Input: $0.075 / 1M
    # Standard Input: $0.30 / 1M
    # Output: $1.20 / 1M (Approx)
    
    std_input_cost = (tracker.input_tokens / 1_000_000) * 0.30
    cached_input_cost = (tracker.input_tokens / 1_000_000) * 0.075
    output_cost = (tracker.output_tokens / 1_000_000) * 1.20
    
    print("\n📊 SIMULATION RESULTS")
    print("---------------------")
    print(f"Games: {NUM_GAMES}")
    print(f"Wins: {wins} ({wins/NUM_GAMES*100}%)")
    print(f"Losses: {losses}")
    print(f"Time: {duration:.2f}s")
    print("\n💰 COST ESTIMATE (Gemini 2.5 Flash)")
    print(f"AI Calls: {tracker.ai_calls}")
    print(f"Input Tokens: {tracker.input_tokens}")
    print(f"Output Tokens: {tracker.output_tokens}")
    print(f"Est Cost (No Cache): ${std_input_cost + output_cost :.4f}")
    print(f"Est Cost (With Cache): ${cached_input_cost + output_cost :.4f}")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ Detailed logs saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    # We patch the database access globally for the sim
    with patch("app.persistence.db", new_callable=MagicMock):
        asyncio.run(main())
