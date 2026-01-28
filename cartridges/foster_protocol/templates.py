import os
from typing import Dict, Any, Tuple
from jinja2 import Environment, FileSystemLoader
from .board import GameConfig
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
# We store the compiled prompt here after the first generation.
_CACHED_BASE_PROMPT = None

def render(template_name: str, **kwargs) -> str:
    template = _ENV.get_template(template_name)
    return template.render(**kwargs)

# --- INTERNAL HELPERS (Private) ---

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

# --- 1. INITIALIZATION COMPOSERS (State Generation) ---
# These return single strings because they set up the 'system_prompt' attribute
# on the Drone object, which is then cached.

def compose_initial_system_prompt(drone_id: str, foster_name: str, is_saboteur: bool) -> str:
    """
    Assembles the massive static system prompt for the drone.
    Includes: Physics Rules + Tools + Specific Identity.
    """
    base = _get_base_prompt()
    identity = _get_identity_block(drone_id, foster_name, is_saboteur)
    # The "Glue" is now here, not in logic.py
    return f"{base}\n\n--- IDENTITY OVERRIDE ---\n{identity}"

def compose_identity_update(drone_id: str, user_id: str, is_saboteur: bool, new_name: str) -> str:
    """
    Reconstructs the system prompt when a drone is renamed.
    """
    # Note: We rely on logic.py to provide the base, or we reconstruct it.
    # For safety/simplicity, we just rebuild the whole thing + the patch.
    # In a real app, you might want to strip the old identity, but rebuilding is safer.
    base = _get_base_prompt()
    identity_block = _get_identity_block(drone_id, user_id, is_saboteur)
    
    update_patch = render("drone_identity_update.md.j2", new_name=new_name)
    
    final_identity = f"{identity_block}\n\n{update_patch}"
    return f"{base}\n\n--- IDENTITY OVERRIDE ---\n{final_identity}"


# --- 2. INTERACTION COMPOSERS (The Tuple Pattern) ---
# All methods below return (system_prompt, user_input)

def compose_intro_turn(cached_system_prompt: str) -> Tuple[str, str]:
    """
    Wake up routine.
    System: The cached drone identity.
    User: The 'Intro' instruction.
    """
    user_input = render("drone_intro.md.j2")
    return cached_system_prompt, user_input

def compose_tactical_turn(context_data: Dict[str, Any]) -> Tuple[str, str]:
    """
    The main game loop turn.
    System: The Tactical Mindset (Short, focused).
    User: Sensor Data + Thought Protocol.
    """
    system = render("drone_day.md.j2")
    
    # User
    context_str = render("turn_context.md.j2", **context_data)
    protocol_str = render("turn_thought_protocol.md.j2", end_hour=GameConfig.HOURS_PER_SHIFT)
    
    user_input = f"{context_str}\n\n{protocol_str}"
    
    return system, user_input

def compose_dream_turn(old_memory: str, daily_logs: list, chat_log: list) -> Tuple[str, str]:
    """
    Memory consolidation.
    System: Blank/Archival (Functional).
    User: The consolidation task.
    """
    system = "You are an archival system."
    user_input = render(
        "dream_consolidation.md.j2",
        old_memory=old_memory,
        daily_logs=daily_logs,
        chat_log=chat_log
    )
    return system, user_input

def compose_nanny_chat_turn(
    cached_system_prompt: str, 
    drone_memory: list, 
    battery: int, 
    location: str, 
    long_term_memory: str, 
    user_message: str,
    drone_name: str = None,
    drone_id: str = None
) -> Tuple[str, str]:
    """
    Night phase chat.
    System: The cached drone identity.
    User: The 'Night Report' context wrapper + User Message.
    """
    recent_logs = drone_memory[-15:]
    
    # logic.py Glue: "IDENTITY: {current_identity}\n"
    current_identity = f"NAME: {drone_name}" if drone_name else f"ID: {drone_id}"
    
    base_context = render(
        "night_report.md.j2",
        drone_memory=recent_logs,
        battery=battery,
        location=location,
        long_term_memory=long_term_memory,
        user_input=user_message
    )
    
    user_input = f"IDENTITY: {current_identity}\n{base_context}"
    return cached_system_prompt, user_input

def compose_speak_turn(cached_system_prompt: str, instruction: str, battery: int) -> Tuple[str, str]:
    """
    Forced speech (e.g. 'Report status').
    """
    user_input = render("drone_speak_instruction.md.j2", instruction=instruction, battery=battery)
    return cached_system_prompt, user_input

def compose_mainframe_turn(user_input: str) -> Tuple[str, str]:
    system = render("mainframe_persona.md.j2")
    # User input is passed directly as the prompt for the Mainframe
    return system, user_input

def compose_eulogy_turn(cached_system_prompt: str) -> Tuple[str, str]:
    user_input = render("drone_eulogy.md.j2")
    return cached_system_prompt, user_input

def compose_epilogue_turn(cached_system_prompt: str, victory: bool, role: str, status_note: str) -> Tuple[str, str]:
    user_input = render("drone_epilogue.md.j2", victory=victory, role=role, status_note=status_note)
    return cached_system_prompt, user_input