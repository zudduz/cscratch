import os

# --- CONSTANTS ---

# System Lifecycle & Logging
LOG_HYDRATING = "System: Hydrating Game Channel Cache..."
LOG_SYNCING = "System: Syncing Slash Commands..."
SYSTEM_ONLINE = "**System Online**"
SYSTEM_OFFLINE = "**System Offline**"

# Channel Operations
BLACK_BOX_OPEN = "**BLACK BOX DECLASSIFIED. LOGS AVAILABLE.**"
CHANNEL_UNKNOWN = "unknown"

# Commands
CMD_VERSION_DESC = "Check container"
CMD_GRP_SCRATCH = "Engine Controls"
CMD_START_DESC = "Open Lobby"
CMD_END_DESC = "Cleanup"

# Lobby & Admin
ADMIN_WARNING = (
    "**FAIR PLAY NOTICE**\n"
    "To the Administrator: You have permissions to view ALL private channels.\n"
    "**FOR A FAIR GAME:** Please **MUTE** or **COLLAPSE** the private channels of other players.\n"
    "*The Protocol relies on trust.*"
)

LOBBY_DESC = "Click to join."
CMD_FAILED = "Failed: {error}"

# Errors & Status
ERR_NO_GAME = "No game."
ERR_NOT_HOST = "Denied. Host only."
MSG_TEARDOWN = "**Teardown.**"

# Interaction UI
BTN_JOIN = "Join"
BTN_START = "Start"
ERR_NOT_HOST_START = "Only the host may start the game"
ERR_GENERIC = "Error"
MSG_STARTING = "Starting game"


# --- LOGIC & FORMATTERS ---

def safe_channel_name(name: str) -> str:
    """Sanitizes a string for use as a Discord channel name."""
    if not name:
        name = CHANNEL_UNKNOWN
    return "".join(c for c in name if c.isalnum() or c == "-").lower()

def format_version_response(revision: str) -> str:
    """Formats the version command response."""
    return f"**Active Node:** `{revision}`"

def format_announcement(message: str) -> str:
    """Formats a system announcement with the current revision ID."""
    rev = os.environ.get('K_REVISION', 'Local-Dev')
    return f"{message}: `{rev}`"

def format_lobby_title(cartridge_name: str) -> str:
    return f"Lobby: {cartridge_name}"

def format_lobby_created_msg(mention: str) -> str:
    return f"Lobby: {mention}"

def format_player_joined(name: str) -> str:
    return f"**{name}** joined!"

def build_cost_report(game_id: str, input_tokens: int, output_tokens: int) -> str:
    """Calculates costs (Gemini 2.5 Flash Pricing) and returns a formatted report."""
    # Pricing: $0.30 per 1M input, $1.25 per 1M output (Updated to user spec if needed, keeping logic central)
    # Note: Previous file had 2.50 for output, sticking to that for consistency with migration
    COST_PER_1M_INPUT = 0.30
    COST_PER_1M_OUTPUT = 2.50

    input_cost = (input_tokens / 1_000_000) * COST_PER_1M_INPUT
    output_cost = (output_tokens / 1_000_000) * COST_PER_1M_OUTPUT
    total_cost = input_cost + output_cost
    
    return (
        f"**GAME {game_id} COST REPORT**\n"
        f"Input: {input_tokens} tok (${input_cost:.4f})\n"
        f"Output: {output_tokens} tok (${output_cost:.4f})\n"
        f"**TOTAL: ${total_cost:.4f}**"
    )