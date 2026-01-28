import os
from typing import Dict, Any, Tuple
from jinja2 import Environment, FileSystemLoader
from .board import GameConfig
from .models import Caisson
from .tools import TOOL_REGISTRY 

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
        context = {k: v for k, v in vars(GameConfig).items() if not k.startswith("__")}
        context["tools"] = list(TOOL_REGISTRY.values())
        context["tool_map"] = TOOL_REGISTRY
        _CACHED_BASE_PROMPT = render("static_prompt.md.j2", **context)
        
    return _CACHED_BASE_PROMPT

def _get_identity_block(drone_id: str, foster_name: str, is_saboteur: bool) -> str:
    return render(
        "drone_identity.md.j2", 
        drone_id=drone_id, 
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

    # 1. Lookup Foster Parent Name
    parent = game_data.players.get(drone.foster_id)
    foster_name = parent.name if parent else "Unknown"
    
    # 2. Get Base (Cached)
    base = _get_base_prompt()
    
    # 3. Get Identity (Dynamic Role/ID)
    identity = _get_identity_block(
        drone_id=drone.id, 
        foster_name=foster_name, 
        is_saboteur=(drone.role == "saboteur")
    )
    
    # 4. Handle Name Override (Dynamic)
    if drone.name:
        patch = render("drone_identity_update.md.j2", new_name=drone.name)
        identity = f"{identity}\n\n{patch}"
        
    return f"{base}\n\n--- IDENTITY OVERRIDE ---\n{identity}"

# --- INTERACTION COMPOSERS ---

def compose_intro_turn(drone_id: str, game_data: Caisson) -> Tuple[str, str]:
    """
    Wake up routine.
    """
    system_prompt = _compose_dynamic_system_prompt(drone_id, game_data)
    user_input = render("drone_intro.md.j2")
    return system_prompt, user_input

def compose_tactical_turn(context_data: Dict[str, Any]) -> Tuple[str, str]:
    """
    The main game loop turn.
    (Note: tactical turn is unique as it uses a shorter 'Tactical Mindset' system prompt, 
    not the full identity prompt, so it doesn't use _compose_dynamic_system_prompt)
    """
    system = render("drone_day.md.j2")
    
    # User
    context_str = render("turn_context.md.j2", **context_data)
    protocol_str = render("turn_thought_protocol.md.j2", end_hour=GameConfig.HOURS_PER_SHIFT)
    
    user_input = f"{context_str}\n\n{protocol_str}"
    return system, user_input

def compose_dream_turn(old_memory: str, daily_logs: list, chat_log: list) -> Tuple[str, str]:
    system = "You are an archival system."
    user_input = render(
        "dream_consolidation.md.j2",
        old_memory=old_memory,
        daily_logs=daily_logs,
        chat_log=chat_log
    )
    return system, user_input

def compose_nanny_chat_turn(
    drone_id: str,
    game_data: Caisson,
    user_message: str
) -> Tuple[str, str]:
    drone = game_data.drones.get(drone_id)
    system_prompt = _compose_dynamic_system_prompt(drone_id, game_data)
    
    recent_logs = drone.daily_memory[-15:]
    
    current_identity = f"NAME: {drone.name}" if drone.name else f"ID: {drone.id}"
    
    base_context = render(
        "night_report.md.j2",
        drone_memory=recent_logs,
        battery=drone.battery,
        location=drone.location_id,
        long_term_memory=drone.long_term_memory,
        user_input=user_message
    )
    
    user_input = f"IDENTITY: {current_identity}\n{base_context}"
    return system_prompt, user_input

def compose_speak_turn(drone_id: str, game_data: Caisson, instruction: str) -> Tuple[str, str]:
    """
    Prompting the Drone to start the conversation speech.
    """
    drone = game_data.drones.get(drone_id)
    system_prompt = _compose_dynamic_system_prompt(drone_id, game_data)
    
    user_input = render("drone_speak_instruction.md.j2", instruction=instruction, battery=drone.battery)
    return system_prompt, user_input

def compose_mainframe_turn(user_input: str) -> Tuple[str, str]:
    system = render("mainframe_persona.md.j2")
    return system, user_input

def compose_eulogy_turn(drone_id: str, game_data: Caisson) -> Tuple[str, str]:
    system_prompt = _compose_dynamic_system_prompt(drone_id, game_data)
    user_input = render("drone_eulogy.md.j2")
    return system_prompt, user_input

def compose_epilogue_turn(drone_id: str, game_data: Caisson, victory: bool, fail_reason: str = "") -> Tuple[str, str]:
    drone = game_data.drones.get(drone_id)
    system_prompt = _compose_dynamic_system_prompt(drone_id, game_data)
    
    context_note = "STATUS: ONLINE."
    if drone.battery <= 0:
        context_note = "STATUS: BATTERY DEAD. Final transmission."
        
    user_input = render(
        "drone_epilogue.md.j2", 
        victory=victory, 
        role=drone.role, 
        status_note=context_note
    )
    return system_prompt, user_input