import os
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader
from .board import GameConfig
from .tools import TOOL_REGISTRY 

# --- JINJA2 SETUP ---
# We assume templates are in the 'prompts/' subdirectory relative to this file.
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROMPTS_DIR = os.path.join(_CURRENT_DIR, "prompts")

# Initialize the environment once
_ENV = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    trim_blocks=True,
    lstrip_blocks=True
)

def render(template_name: str, **kwargs) -> str:
    """Helper to render a template by name with given context."""
    template = _ENV.get_template(template_name)
    return template.render(**kwargs)

# --- PROMPT ACCESSORS ---

def get_base_prompt() -> str:
    """
    Renders the main system prompt with game configuration constants.
    """
    # 1. GameConfig constants (Refactored for Class)
    # We iterate over class attributes, ignoring internal dunder methods
    context = {k: v for k, v in vars(GameConfig).items() if not k.startswith("__")}

    # 2. Inject Tools for dynamic looping (Step 2 Prep)
    # We convert values to a list so Jinja can iterate easily
    context["tools"] = list(TOOL_REGISTRY.values())
    
    # 3. Inject Tool Map for direct access (e.g. {{ tool_map['move'].COST }})
    context["tool_map"] = TOOL_REGISTRY

    return render("static_prompt.md.j2", **context)

def get_mainframe_prompt() -> str:
    return render("mainframe_persona.md.j2")

def get_drone_identity_block(drone_id: str, foster_name: str, is_saboteur: bool) -> str:
    """
    Returns only the specific identity instruction for the drone.
    """
    return render(
        "drone_identity.md.j2", 
        drone_id=drone_id, 
        foster_name=foster_name, 
        is_saboteur=is_saboteur
    )

def get_night_context(drone_memory: list, battery: int, location: str, long_term_memory: str, user_input: str) -> str:
    """
    Constructs the context for the Night Phase (Nanny Port) chat.
    """
    # We slice the memory here to match the old logic (last 15 entries)
    recent_logs = drone_memory[-15:]
    
    return render(
        "night_report.md.j2",
        drone_memory=recent_logs,
        battery=battery,
        location=location,
        long_term_memory=long_term_memory,
        user_input=user_input
    )

def get_dream_prompt(old_memory: str, daily_logs: list, chat_log: list) -> str:
    """
    Constructs the prompt for memory consolidation (Dreaming).
    """
    return render(
        "dream_consolidation.md.j2",
        old_memory=old_memory,
        daily_logs=daily_logs,
        chat_log=chat_log
    )

# --- NEW ACCESSORS ---

def get_intro_prompt() -> str:
    return render("drone_intro.md.j2")

def get_turn_context(data: Dict[str, Any]) -> str:
    return render("turn_context.md.j2", **data)

def get_thought_protocol() -> str:
    # We pass end_hour for the logic check in the prompt
    return render("turn_thought_protocol.md.j2", end_hour=GameConfig.HOURS_PER_SHIFT)

def get_speak_prompt(instruction: str, battery: int) -> str:
    return render("drone_speak_instruction.md.j2", instruction=instruction, battery=battery)

def get_eulogy_prompt() -> str:
    return render("drone_eulogy.md.j2")

def get_epilogue_prompt(victory: bool, role: str, status_note: str) -> str:
    return render("drone_epilogue.md.j2", victory=victory, role=role, status_note=status_note)

def get_identity_update_prompt(new_name: str) -> str:
    return render("drone_identity_update.md.j2", new_name=new_name)