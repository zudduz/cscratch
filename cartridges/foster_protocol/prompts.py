import os
from jinja2 import Environment, FileSystemLoader
from .board import GameConfig
from .tools import *

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
    return render(
        "system_prompt_template.md",
        HOURS_PER_SHIFT=GameConfig.HOURS_PER_SHIFT,
        CAPACITY_TORPEDO_BAY=GameConfig.CAPACITY_TORPEDO_BAY,
        CAPACITY_SHUTTLE_BAY=GameConfig.CAPACITY_SHUTTLE_BAY,
        TORPEDO_RISK_PERCENT=GameConfig.TORPEDO_ACCIDENT_PERCENT,
        OXYGEN_VENT_AMOUNT=GameConfig.OXYGEN_VENT_AMOUNT,
        PLASMA_TORCH_DISCOVERY_PERCENT=GameConfig.PLASMA_TORCH_DISCOVERY_PERCENT,
        
        COST_MOVE=ActionCosts.MOVE,
        COST_GATHER=ActionCosts.GATHER,
        COST_DEPOSIT=ActionCosts.DEPOSIT,
        COST_TOW=ActionCosts.TOW,
        COST_DRAIN=ActionCosts.DRAIN,
        COST_SABOTAGE=ActionCosts.SABOTAGE,
        COST_KILL=ActionCosts.KILL,
        COST_DETONATE=ActionCosts.DETONATE
    )

def get_mainframe_prompt() -> str:
    return render("mainframe_persona.md")

def get_drone_identity_block(drone_id: str, foster_name: str, is_saboteur: bool) -> str:
    """
    Returns only the specific identity instruction for the drone.
    """
    return render(
        "drone_identity.md", 
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
        "night_report.md",
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
        "dream_consolidation.md",
        old_memory=old_memory,
        daily_logs=daily_logs,
        chat_log=chat_log
    )