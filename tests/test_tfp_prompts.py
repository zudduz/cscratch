import pytest
import os
from jinja2 import Environment, FileSystemLoader, StrictUndefined

# Define path relative to this test file
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "../cartridges/foster_protocol/prompts")

# --- THE UNIVERSAL CONTEXT ---
# This dictionary contains dummy values for EVERY variable used in your templates.
# If you add a NEW variable to a template (e.g. {{ weapon_type }}), add a dummy value here.
# You do NOT need to update this if you just change text or logic logic.
DUMMY_CONTEXT = {
    # System / Board Config (from system_prompt_template.md)
    "HOURS_PER_SHIFT": 8,
    "CAPACITY_TORPEDO_BAY": 100,
    "CAPACITY_SHUTTLE_BAY": 50,
    "TORPEDO_RISK_PERCENT": 5,
    "OXYGEN_VENT_AMOUNT": 10,
    "PLASMA_TORCH_DISCOVERY_CHANCE": 0.2,
    "COST_MOVE": 5,
    "COST_GATHER": 5,
    "COST_DEPOSIT": 5,
    "COST_TOW": 10,
    "COST_DRAIN": 5,
    "COST_SABOTAGE": 10,
    "COST_KILL": 20,
    "COST_DETONATE": 50,

    # Drone Identity
    "drone_id": "UNIT_TEST_01",
    "foster_name": "Test Subject",
    "is_saboteur": True,

    # Night Report
    "battery": 75,
    "location": "shasis_bay",
    "long_term_memory": "I am a drone. I love my parent.",
    "drone_memory": ["Log 1: Woke up.", "Log 2: Ate batteries."],
    "user_input": "Good job, drone.",

    # Dream Consolidation
    "old_memory": "Previous memory state.",
    "daily_logs": ["Day Log A", "Day Log B"],
    "chat_log": ["Parent: Hi", "Me: Hello"],
    
    # Future-proofing (for tools.py migration)
    "tools": [], 
    "visible_drones": ["unit_02"],
    "objective": "Survive"
}

def get_template_files():
    """Auto-discovers all .md files in the prompts directory."""
    if not os.path.exists(PROMPTS_DIR):
        return []
    return [f for f in os.listdir(PROMPTS_DIR) if f.endswith(".md")]

@pytest.fixture(scope="module")
def strict_env():
    """
    Creates a Jinja2 environment that raises errors for undefined variables.
    This catches typos like {{ batery }} instead of {{ battery }}.
    """
    return Environment(
        loader=FileSystemLoader(PROMPTS_DIR),
        undefined=StrictUndefined,  # <--- The magic safety switch
        trim_blocks=True,
        lstrip_blocks=True
    )

@pytest.mark.parametrize("template_file", get_template_files())
def test_template_integrity(strict_env, template_file):
    """
    Renders every template with the dummy context.
    Fails if:
    1. Syntax is invalid (e.g. unclosed {% if %})
    2. A variable is missing from DUMMY_CONTEXT
    """
    try:
        template = strict_env.get_template(template_file)
        rendered = template.render(**DUMMY_CONTEXT)
        
        # Sanity Checks
        assert len(rendered) > 0, "Template rendered an empty string."
        assert "{{" not in rendered, f"Found unrendered variable marker '{{{{' in {template_file}."
        assert "%}" not in rendered, f"Found unrendered logic marker '%}}' in {template_file}."

    except Exception as e:
        pytest.fail(f"Template '{template_file}' failed to compile: {e}")