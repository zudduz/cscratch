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
    # Keys must match the {KEY} format in the template exactly
    context = {
        "{HOURS_PER_SHIFT}": str(GameConfig.HOURS_PER_SHIFT),
        "{CAPACITY_TORPEDO_BAY}": str(GameConfig.CAPACITY_TORPEDO_BAY),
        "{CAPACITY_SHUTTLE_BAY}": str(GameConfig.CAPACITY_SHUTTLE_BAY),
        "{TORPEDO_RISK_PERCENT}": str(int(GameConfig.TORPEDO_ACCIDENT_CHANCE * 100)),
        
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
        # Perform Search & Replace
        # We use replace() instead of format() so we don't have to escape
        # the thousands of JSON braces { } in the file.
        final_text = template
        for key, value in context.items():
            if key not in final_text:
                print(f"⚠️ Warning: Variable {key} defined but not found in template.")
            final_text = final_text.replace(key, value)
        
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(final_text)
            
        print(f"✅ Generated: {OUTPUT_PATH}")
        print(f"   - Injected {len(context)} constants.")

    except Exception as e:
        print(f"❌ Error during compilation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    compile()
