import os
import sys

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
        "HOURS_PER_SHIFT": GameConfig.HOURS_PER_SHIFT,
        "CAPACITY_TORPEDO_BAY": GameConfig.CAPACITY_TORPEDO_BAY,
        "CAPACITY_SHUTTLE_BAY": GameConfig.CAPACITY_SHUTTLE_BAY,
        "TORPEDO_RISK_PERCENT": int(GameConfig.TORPEDO_ACCIDENT_CHANCE * 100),
        
        # Costs
        "COST_MOVE": ActionCosts.MOVE,
        "COST_GATHER": ActionCosts.GATHER,
        "COST_DEPOSIT": ActionCosts.DEPOSIT,
        "COST_TOW": ActionCosts.TOW,
        "COST_DRAIN": ActionCosts.DRAIN,
        "COST_SABOTAGE": ActionCosts.SABOTAGE,
        "COST_KILL": ActionCosts.KILL,
        "COST_DETONATE": ActionCosts.DETONATE,
    }

    try:
        # Perform the substition
        final_text = template.format(**context)
        
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(final_text)
            
        print(f"✅ Generated: {OUTPUT_PATH}")
        print(f"   - Injected {len(context)} variables.")

    except KeyError as e:
        print(f"❌ Compilation Failed: Template contains {{key}} not found in context: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    compile()
