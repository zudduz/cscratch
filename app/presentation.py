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
    "**Fair play notice**\n"
    "To the Administrator: You have permissions to view all private channels.\n"
    "**FOR A FAIR GAME:** Please **mute** or **collapse** the private channels of other players.\n"
)

LOBBY_DESC = "Click to join"
CMD_FAILED = "Failed: {error}"

# Errors & Status
ERR_NO_GAME = "No game"
ERR_NOT_HOST = "Denied\nHost only"
ERR_DENIED_ADMIN = "Denied\nAdmin access required"
MSG_TEARDOWN = "Teardown"

# Interaction UI
BTN_JOIN = "Join"
BTN_START = "Start"
BTN_DELETE_CHANNELS = "Delete Channels"

EMBED_TITLE_ENDED = "Game Complete"
EMBED_DESC_ENDED = "The host may now delete the channels"

ERR_NOT_HOST_START = "Only the host may start the game"
ERR_GENERIC = "Error"
MSG_STARTING = "Starting game"
GAME_ALREADY_STARTED = "Game already started"
LOBBY_FULL = "Lobby is full"


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

def format_player_joined(name: str, count: int, max_p: int, cost: int) -> str:
    return f"**{name}** joined! ({count}/{max_p})\nStart button will cost {cost} scratch"

def build_cost_report(game_id: str, input_tokens: int, output_tokens: int) -> str:
    """Calculates costs (Gemini 2.5 Flash Pricing) and returns a formatted report."""
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

def format_balance_report(user_id: str, balance: int) -> str:
    return f"<@{user_id}>, your balance is **{balance}** Scratch."

def format_gift_report(amount: int, target_id: str, new_balance: int) -> str:
    return f"**System Gift**\nSent **{amount}** Scratch to <@{target_id}>.\nNew Balance: {new_balance}"

def format_admin_balance_report(target_id: str, balance: int) -> str:
    return f"User <@{target_id}> balance: **{balance}** Scratch"

def insufficient_funds(balance: int, cost: int) -> str:
    return f"This game costs {cost} Scratch to start\nPlease purchase more Scratch"