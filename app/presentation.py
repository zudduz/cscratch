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
CMD_LOBBY_DESC = "Open Lobby"
CMD_KILL_DESC = "Cleanup"

# Lobby & Admin
LOBBY_DESC = "Click to join"
MSG_LOBBY_INSTRUCTIONS = 'Send "/cscratch guide" for how to play the game'
CMD_FAILED = "Failed: {error}"

# Errors & Status
ERR_NO_GAME = "No game"
ERR_NO_ACTIVE_GAME = "No active game"
ERR_NOT_HOST = "Denied\nHost only"
ERR_DENIED_ADMIN = "Denied\nAdmin access required"
ERR_NO_CATEGORY = "You must run this command inside a designated game category."
ERR_CATEGORY_FULL = "The server's game category is full (Discord 50-channel limit). Please wait for a game to end."
ERR_DOC_NOT_FOUND = "{doc_name} not found for this cartridge"
ERR_DOC_LOAD_FAILED = "Failed to load {doc_name}: {error}"

# Interaction UI
BTN_JOIN = "Join"
BTN_START = "Start"
BTN_DELETE_CHANNELS = "Delete Channels"

EMBED_DESC_ENDED = "The host may now delete the channels"

ERR_NOT_HOST_START = "Only the host may start the game"
ERR_GENERIC = "Error"
MSG_STARTING = "Starting game..."

# --- LOGIC & FORMATTERS ---

def format_admin_warning(admin_name: str) -> str:
    return (
        f"**Fair play notice for {admin_name}**\n"
        "To the Administrator: You have permissions to view all private channels.\n"
        "**FOR A FAIR GAME:** Please **mute** or **collapse** the private channels of other players.\n"
    )

def format_teardown(lobby_name: str) -> str:
    return f"Teardown initiated for {lobby_name}"

def format_lobby_full(lobby_name: str) -> str:
    return f"{lobby_name} is full"

def format_game_already_started(lobby_name: str) -> str:
    return f"{lobby_name} has already started"

def format_game_complete_title(lobby_name: str) -> str:
    return f"Game Complete: {lobby_name}"

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

def format_lobby_title(cartridge_name: str, callsign: str) -> str:
    return f"Lobby [{callsign}]: {cartridge_name}"

def format_game_started(callsign: str, cartridge: str) -> str:
    lobby_name = format_lobby_title(cartridge, callsign)
    return f"**Game Started for {lobby_name}!**\nYour callsign is **{callsign}**.\nProceed to your newly created channels."

def format_player_joined(name: str, count: int, max_p: int, cost: int, lobby_name: str) -> str:
    return f"**{name}** joined {lobby_name}! ({count}/{max_p})\nStart button will cost {cost} scratch"

def build_cost_report(game_id: str, callsign: str, input_tokens: int, output_tokens: int) -> str:
    """Calculates costs (Gemini 2.5 Flash Pricing) and returns a formatted report."""
    COST_PER_1M_INPUT = 0.30
    COST_PER_1M_OUTPUT = 2.50

    input_cost = (input_tokens / 1_000_000) * COST_PER_1M_INPUT
    output_cost = (output_tokens / 1_000_000) * COST_PER_1M_OUTPUT
    total_cost = input_cost + output_cost
    
    return (
        f"**GAME {game_id} [{callsign}] COST REPORT**\n"
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