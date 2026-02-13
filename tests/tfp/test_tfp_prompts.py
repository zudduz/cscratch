import pytest
import os
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from cartridges.foster_protocol.models import Drone
from cartridges.foster_protocol.board import GameConfig
from cartridges.foster_protocol.tools import TOOL_REGISTRY

# Define path relative to this test file
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "../../cartridges/foster_protocol/ai_templates")

# --- THE UNIVERSAL CONTEXT ---
# This dictionary contains dummy values for EVERY variable used in your templates.
# If you add a NEW variable to a template (e.g. {{ weapon_type }}), add a dummy value here.

# 1. Start with GameConfig constants
# Updated to extract from Class instead of Enum
DUMMY_CONTEXT = {k: v for k, v in vars(GameConfig).items() if not k.startswith("__")}

# 2. Inject Tools for dynamic looping
DUMMY_CONTEXT["tools"] = list(TOOL_REGISTRY.values())

# 3. Inject Tool Map for direct access (e.g. {{ tool_map['move'].COST }})
DUMMY_CONTEXT["tool_map"] = TOOL_REGISTRY

# 4. Add specific variable overrides for tests
DUMMY_CONTEXT.update({
    # Drone Identity
    "drone_id": "UNIT_TEST_01",
    "drone": Drone(id="unit_301", battery=75, location_id="engine_room", inventory=["fuel_canister", "plasma_torch"],
        long_term_memory="I am a drone. I love my foster.",
        drone_memory=["Log 1: Woke up.", "Log 2: Ate batteries."],
    ),
    "foster_name": "Test Subject",
    "is_saboteur": True,
    "is_first_message": True,
    "role": "saboteur",
    "new_name": "Unit-Alpha",

    # Night Report
    "battery": 75,
    "location": "stasis_bay",
    "location_id": "engine_room",
    "long_term_memory": "I am a drone. I love my foster.",
    "drone_memory": ["Log 1: Woke up.", "Log 2: Ate batteries."],
    "user_input": "Good job, drone.",
    "chat_history": ["Foster: You like apples?", "You:Absolutely!"],

    # Dream Consolidation
    "old_memory": "Previous memory state.",
    "daily_logs": ["Day Log A", "Day Log B"],
    "chat_log": ["Foster: Hi", "Me: Hello"],
    
    # Tools & Turn Context (Overrides/Specifics)
    "visible_drones": ["unit_02"],
    "hour": 7,
    "end_hour": 8,
    "inventory": ["fuel_canister", "plasma_torch"],
    "schema": "schema",
    "daily_memory": ["Stared at the wall for 5 hours", "Ate a carrot but failed because I'm not a biological entity"],
    
    # Instructions & Speak
    "instruction": "Report status.",
    
    # Epilogue / Eulogy
    "game_end_state": "no_active_drones",
})

def get_template_files():
    """Auto-discovers all .md files in the templates directory."""
    if not os.path.exists(TEMPLATES_DIR):
        return []
    return [f for f in os.listdir(TEMPLATES_DIR) if f.endswith(".md.j2")]

@pytest.fixture(scope="module")
def strict_env():
    """
    Creates a Jinja2 environment that raises errors for undefined variables.
    This catches typos like {{ batery }} instead of {{ battery }}.
    """
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
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