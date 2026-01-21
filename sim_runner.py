import asyncio
import os
import json
import random
import time
import warnings
import urllib3
import subprocess
import sys

# --- NETWORK STABILIZATION ---
adapter = urllib3.PoolManager(maxsize=50) 
warnings.filterwarnings("ignore", message="Your application has authenticated using end user credentials")

from unittest.mock import MagicMock, AsyncMock, patch
from cartridges.foster_protocol.logic import FosterProtocol
from cartridges.foster_protocol.models import CaissonState, PlayerState
from app.engine_context import EngineContext
from app.ai_engine import AIEngine

# CONFIG
NUM_GAMES = 3
MAX_DAYS = 10
MAX_CONCURRENT_GAMES = 3  # Parallel Execution
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
real_ai = AIEngine()

async def tracked_generate_response(system_prompt, conversation_id, user_input, model_version, game_id=None):
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_input)]
        
        # Add slight jitter to prevent exact simultaneous API hits
        await asyncio.sleep(random.uniform(0.1, 0.5))
        
        model = await real_ai._get_model(model_version)
        
        for attempt in range(3):
            try:
                result = await model.ainvoke(messages)
                tracker.add(result.response_metadata)
                
                content = result.content
                if isinstance(content, list):
                    text_parts = [part.get("text", "") if isinstance(part, dict) else str(part) for part in content]
                    content = "".join(text_parts)
                return content
            except Exception as e:
                if "429" in str(e):
                    wait_time = (2 ** attempt) + random.random()
                    print(f"⚠️ Rate Limit. Retrying in {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
                else:
                    raise e
        return '{"tool": "wait", "args": {}}' 
    except Exception as e:
        print(f"AI Error: {e}")
        return '{"tool": "wait", "args": {}}'

class SimContext:
    def __init__(self, game_id, log_file):
        self.game_id = game_id
        self.log_file = log_file
        self.trigger_data = {}
        self.logs = []
        
        # Clear/Create log file
        with open(self.log_file, "w") as f:
            f.write(f"--- LOG START: {game_id} ---\n")
    
    async def send(self, channel, message):
        log_entry = f"[{channel}] {message}"
        self.logs.append(log_entry)
        
        # Write to specific game file
        with open(self.log_file, "a") as f:
            f.write(log_entry + "\n")

        # Minimal console output to show aliveness
        if channel in ["black-box", "aux-comm"]:
            print(f"[{self.game_id}] {message}")

    async def reply(self, message):
        pass
        
    def schedule(self, coro):
        pass 

    async def end(self):
        with open(self.log_file, "a") as f:
            f.write("--- GAME END ---\n")

async def run_single_game(game_idx, semaphore):
    async with semaphore:
        log_filename = f"game_{game_idx}.log"
        print(f"▶️ Game {game_idx} Starting... (Logs -> {log_filename})")
        
        cartridge = FosterProtocol()
        players = [
            {"id": "p1", "name": "Alice"},
            {"id": "p2", "name": "Bob"},
            {"id": "p3", "name": "Charlie"},
            {"id": "p4", "name": "Dave"},
            {"id": "p5", "name": "Eve"}
        ]
        
        start_data = await cartridge.on_game_start({"players": players})
        game_data = CaissonState(**start_data["metadata"])
        ctx = SimContext(f"sim_{game_idx}", log_filename)
        
        mock_tools = MagicMock()
        mock_tools.ai.generate_response = tracked_generate_response
        
        victory = False
        fail_reason = "Time Limit"
        
        try:
            for day in range(1, MAX_DAYS + 1):
                # Write Day Header to file
                with open(log_filename, "a") as f:
                    f.write(f"\n=== DAY {day} ===\n")
                    
                for p in game_data.players.values(): p.is_sleeping = False
                
                await cartridge.execute_day_simulation(game_data, ctx, mock_tools)
                
                if any("[WIN]" in log for log in ctx.logs):
                    victory = True
                    break
                if any("[FAIL]" in log for log in ctx.logs):
                    victory = False
                    fail_reason = "Mission Failure"
                    break
        except Exception as e:
            print(f"❌ Game {game_idx} Crashed: {e}")
            fail_reason = f"Crash: {str(e)}"

        result_symbol = "✅ WIN" if victory else "❌ LOSS"
        print(f"🏁 Game {game_idx} Finished: {result_symbol} ({fail_reason})")
        
        return {
            "id": game_idx,
            "victory": victory,
            "reason": fail_reason,
            "end_oxygen": game_data.oxygen,
            "end_fuel": game_data.fuel
        }

async def main():
    # --- AUTO-COMPILE PROMPTS ---
    print("🔨 COMPILING PROMPTS...")
    try:
        subprocess.run([sys.executable, "compile_prompts.py"], check=True)
        print("✅ Compilation Complete.")
    except Exception as e:
        print(f"⚠️ Compilation skipped/failed: {e}")

    print(f"🚀 INITIALIZING PARALLEL SIMULATION ({NUM_GAMES} Games)...")
    print("-------------------------------------------------------")
    
    start_time = time.time()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_GAMES)
    
    # Create tasks for simultaneous execution
    tasks = [run_single_game(i, semaphore) for i in range(1, NUM_GAMES + 1)]
    results = await asyncio.gather(*tasks)
    
    duration = time.time() - start_time
    wins = sum(1 for r in results if r['victory'])
    
    cached_input_cost = (tracker.input_tokens / 1_000_000) * 0.075
    output_cost = (tracker.output_tokens / 1_000_000) * 1.25
    
    print("\n📊 SIMULATION RESULTS")
    print("---------------------")
    print(f"Games: {NUM_GAMES} | Wins: {wins} | Losses: {NUM_GAMES - wins}")
    print(f"Time: {duration:.2f}s")
    print("\n💰 COST ESTIMATE")
    print(f"AI Calls: {tracker.ai_calls}")
    print(f"Input Tokens: {tracker.input_tokens}")
    print(f"Output Tokens: {tracker.output_tokens}")
    print(f"Est Cost (With Cache hit): ${cached_input_cost + output_cost :.4f}")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    with patch("app.persistence.db", new_callable=MagicMock):
        asyncio.run(main())
