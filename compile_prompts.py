import os
import sys
import re

# Ensure we can import from the local modules
sys.path.append(os.getcwd())

from cartridges.foster_protocol.board import GameConfig, SHIP_MAP, ActionCosts

TEMPLATE_PATH = "cartridges/foster_protocol/prompts/system_prompt_template.md"
OUTPUT_PATH = "cartridges/foster_protocol/prompts/final_system_prompt.md"

def compile():
    print(f"🔨 Compiling Prompts...")
    
    if not os.path.exists(TEMPLATE_PATH):
        print(f"❌ Error: Template not found at {TEMPLATE_PATH}")
        sys.exit(1)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    # Define the Context Dictionary
    context = {
        "{HOURS_PER_SHIFT}": str(GameConfig.HOURS_PER_SHIFT),
        "{CAPACITY_TORPEDO_BAY}": str(GameConfig.CAPACITY_TORPEDO_BAY),
        "{CAPACITY_SHUTTLE_BAY}": str(GameConfig.CAPACITY_SHUTTLE_BAY),
        "{TORPEDO_RISK_PERCENT}": str(int(GameConfig.TORPEDO_ACCIDENT_CHANCE * 100)),
        "{OXYGEN_VENT_AMOUNT}": str(GameConfig.OXYGEN_VENT_AMOUNT),
        
        # Costs
        "{COST_MOVE}": str(ActionCosts.MOVE),
        "{COST_GATHER}": str(ActionCosts.GATHER),
        "{COST_DEPOSIT}": str(ActionCosts.DEPOSIT),
        "{COST_TOW}": str(ActionCosts.TOW),
        "{COST_DRAIN}": str(ActionCosts.DRAIN),
        "{COST_SABOTAGE}": str(ActionCosts.SABOTAGE),
        "{COST_KILL}": str(ActionCosts.KILL),
        "{COST_DETONATE}": str(ActionCosts.DETONATE),
    }

    try:
        final_text = template
        used_keys = set()

        for key, value in context.items():
            if key in final_text:
                final_text = final_text.replace(key, value)
                used_keys.add(key)
        
        unused_keys = set(context.keys()) - used_keys
        if unused_keys:
            print(f"❌ Build Failed: The following config variables were NOT found in the template:")
            for k in unused_keys:
                print(f"   - {k}")
            sys.exit(1)

        leftover_pattern = r"\{[A-Z][A-Z0-9_]+\}" 
        leftovers = re.findall(leftover_pattern, final_text)
        
        if leftovers:
            print(f"❌ Build Failed: Found potential unreplaced variables in the output:")
            for m in set(leftovers):
                print(f"   - {m}")
            sys.exit(1)

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(final_text)
            
        print(f"✅ Generated: {OUTPUT_PATH}")
        print(f"   - Verified {len(context)} variables.")

    except Exception as e:
        print(f"❌ Error during compilation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    compile()
