import logging
import discord
from discord import app_commands
from discord.ext import commands

# Relative Imports
from . import game_engine
from . import persistence

# --- Bot Setup ---
class ChickenBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True # Still needed to read game chat
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        
        # The Cache: A set of channel IDs that we should listen to
        self.active_game_channels = set()

    async def setup_hook(self):
        # 1. Hydrate Cache
        logging.info("System: Hydrating Game Channel Cache...")
        self.active_game_channels = await persistence.get_active_game_channels()
        
        # 2. Sync Slash Commands
        # In prod, you might want to sync only when needed to avoid rate limits
        logging.info("System: Syncing Slash Commands...")
        await self.tree.sync()

# Initialize the Bot
client = ChickenBot()

# --- SLASH COMMANDS (The Lobby) ---

@client.tree.command(name="start", description="Boot a game cartridge")
@app_commands.describe(cartridge="The Story ID (default: hms-bucket)")
async def start(interaction: discord.Interaction, cartridge: str = "hms-bucket"):
    # Slash commands require an immediate response (or deferral)
    await interaction.response.defer()

    try:
        # 1. Start Game
        game_id = await game_engine.start_new_game(story_id=cartridge)
        
        # 2. Build UI (The Blueprint)
        guild = interaction.guild
        category = await guild.create_category(f"Game {game_id}")
        channel = await guild.create_text_channel("bucket-deck", category=category)
        
        # 3. Register Interface
        await game_engine.register_interface(game_id, {
            "type": "discord",
            "guild_id": str(guild.id),
            "channel_id": str(channel.id),
            "category_id": str(category.id)
        })
        
        # 4. Update Cache
        client.active_game_channels.add(str(channel.id))
        
        # 5. Respond
        await interaction.followup.send(f"🚀 **Cartridge Loaded:** {cartridge}\nID: `{game_id}`\nLocation: {channel.mention}")
        await channel.send("**HMS Bucket**\n*System Online. Waiting for input...*")
        
    except Exception as e:
        logging.error(f"Slash Command Error: {e}")
        await interaction.followup.send(f"❌ Failed to start game: {str(e)}")

@client.tree.command(name="nuke", description="Admin: Delete game channels")
@app_commands.describe(match="Name pattern to delete")
async def nuke(interaction: discord.Interaction, match: str):
    await interaction.response.defer(ephemeral=True)
    
    # Check Admin permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("❌ You need Admin permissions.")
        return

    deleted = 0
    # Iterate through all channels in the server
    for channel in interaction.guild.channels:
        if match in channel.name:
            await channel.delete()
            # Note: We should technically remove from cache here, 
            # but it will clean itself up on next restart (or rely on game status check).
            deleted += 1
            
    await interaction.followup.send(f"☢️ Nuked {deleted} channels matching '{match}'")

# --- GAMEPLAY LISTENER (The Game) ---

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # --- THE FIREHOSE FILTER ---
    # Instant check: Is this channel in our active game list?
    # If not, we return immediately. This saves 99% of processing.
    if str(message.channel.id) not in client.active_game_channels:
        return

    # --- IDEMPOTENCY CHECK ---
    # Only lock events that pass the filter
    if not await persistence.lock_event(message.id):
        return

    # --- GAME ENGINE ---
    try:
        # Show typing indicator while thinking
        async with message.channel.typing():
            response_text = await game_engine.process_player_input(
                channel_id=message.channel.id,
                user_input=message.content
            )
        
        if response_text:
            await message.channel.send(response_text)
            
    except Exception as e:
        logging.error(f"Gameplay Error: {e}")
