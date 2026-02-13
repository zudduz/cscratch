import os
from typing import Dict, Any, Tuple
from jinja2 import Environment, FileSystemLoader
from .board import GameConfig
from .models import Caisson, Drone

SCHEMA_THOUGHT_CHAIN_DESC = "Room for your thoughts."
SCHEMA_TOOL_DESC_PREFIX = "The tool to execute."
SCHEMA_ARGS_DESC = "Arguments for the selected tool (e.g., target_id, room_id)."

# --- JINJA2 SETUP ---
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_TEMPLATES_DIR = os.path.join(_CURRENT_DIR, "ai_templates")

_ENV = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    trim_blocks=True,
    lstrip_blocks=True
)

# --- CACHE STORAGE ---
_CACHED_BASE_PROMPT = None

def render(template_name: str, **kwargs) -> str:
    template = _ENV.get_template(template_name)
    return template.render(**kwargs)

# --- INTERNAL HELPERS ---

def _get_base_prompt() -> str:
    """
    Returns the static base prompt.
    Generates it once and caches it for the lifetime of the process.
    """
    global _CACHED_BASE_PROMPT
    
    if _CACHED_BASE_PROMPT is None:
        # Import internally to avoid Circular Import with tools.py
        from .tools import TOOL_REGISTRY
        
        context = {k: v for k, v in vars(GameConfig).items() if not k.startswith("__")}
        context["tools"] = list(TOOL_REGISTRY.values())
        context["tool_map"] = TOOL_REGISTRY
        _CACHED_BASE_PROMPT = render("static_prompt.md.j2", **context)
        
    return _CACHED_BASE_PROMPT

def _get_identity_block(drone: Drone, foster_name: str, is_saboteur: bool) -> str:
    return render(
        "drone_identity.md.j2", 
        drone=drone, 
        foster_name=foster_name, 
        is_saboteur=is_saboteur
    )

def _compose_dynamic_system_prompt(drone_id: str, game_data: Caisson) -> str:
    """
    Dynamically assembles the full system prompt based on current game state.
    """
    drone = game_data.drones.get(drone_id)
    if not drone:
        return "SYSTEM ERROR: Drone Identity Not Found."

    # 1. Lookup Foster Name
    foster = game_data.players.get(drone.foster_id)
    foster_name = foster.name if foster else "Unknown"
    
    # 2. Get Base (Cached)
    base = _get_base_prompt()
    
    # 3. Get Identity (Dynamic Role/ID)
    identity = _get_identity_block(
        drone=drone, 
        foster_name=foster_name, 
        is_saboteur=(drone.role == "saboteur")
    )
        
    return f"{base}\n\n{identity}"

# --- INTERACTION COMPOSERS ---

def compose_intro_turn(drone_id: str, game_data: Caisson) -> Tuple[str, str]:
    """
    Wake up routine.
    """
    system_prompt = _compose_dynamic_system_prompt(drone_id, game_data)
    user_input = render("drone_intro.md.j2")
    return system_prompt, user_input

def compose_tactical_turn(drone: Drone, game_data: Caisson, hour: int) -> Tuple[str, str]:
    """
    The main game loop turn.
    """
    context_data = _gather_turn_context_data(drone, game_data, hour)
    
    system_prompt = _compose_dynamic_system_prompt(drone.id, game_data)
    user_input = render("turn_context.md.j2", **context_data)
    
    return system_prompt, user_input

def _gather_turn_context_data(drone: Drone, game_data: Caisson, hour: int = 1) -> Dict[str, Any]:
    """
    Gathers raw data for the turn context prompt.
    """
    visible_drones = [
        f"{d.id} ({d.status})"
        for d in game_data.drones.values() 
        if d.location_id == drone.location_id and d.id != drone.id
    ]
    
    return {
        "hour": hour,
        "end_hour": GameConfig.HOURS_PER_SHIFT,
        "location_id": drone.location_id,
        "battery": drone.battery,
        "inventory": drone.inventory,
        "visible_drones": visible_drones,
        "long_term_memory": drone.long_term_memory,
        "daily_activity_log": drone.daily_memory
    }

def compose_dream_turn(old_memory: str, daily_logs: list, chat_log: list) -> Tuple[str, str]:
    system = "You are an archival system."
    user_input = render(
        "dream_consolidation.md.j2",
        old_memory=old_memory,
        daily_logs=daily_logs,
        chat_log=chat_log
    )
    return system, user_input

def compose_nanny_chat_turn(drone_id: str, game_data: Caisson, user_message: str) -> Tuple[str, str]:
    return _compose_night_report(drone_id, game_data, False, user_message)

def compose_speak_turn(drone_id: str, game_data: Caisson) -> Tuple[str, str]:
    return _compose_night_report(drone_id, game_data, True)

def _compose_night_report(drone_id: str, game_data: Caisson, is_first_message: bool, user_message: str = "") -> Tuple[str, str]:
    drone = game_data.drones.get(drone_id)
    system_prompt = _compose_dynamic_system_prompt(drone_id, game_data)
    
    recent_logs = drone.daily_memory[-15:]

    user_input = render(
        "night_report.md.j2",
        drone=drone,
        drone_memory=recent_logs,
        user_input=user_message,
        is_first_message=is_first_message,
        chat_history=drone.night_chat_log
    )

    return system_prompt, user_input
    

def compose_mainframe_turn(user_input: str) -> Tuple[str, str]:
    system = render("mainframe_persona.md.j2")
    return system, user_input

def compose_eulogy_turn(drone_id: str, game_data: Caisson) -> Tuple[str, str]:
    system_prompt = _compose_dynamic_system_prompt(drone_id, game_data)
    user_input = render("drone_eulogy.md.j2")
    return system_prompt, user_input

def compose_epilogue_turn(drone_id: str, game_data: Caisson, game_end_state) -> Tuple[str, str]:
    drone = game_data.drones.get(drone_id)
    system_prompt = _compose_dynamic_system_prompt(drone_id, game_data)
    
    user_input = render(
        "drone_epilogue.md.j2", 
        game_end_state=game_end_state
    )
    return system_prompt, user_input

def format_foster_log_line(input: str) -> str:
    return f"FOSTER: {input}"
