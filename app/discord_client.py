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
        intents.message_content = True 
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        
        # The Cache: A set of channel IDs that we should listen to
        self.active_game_channels = set()

    async def setup_hook(self):
        # 1. Hydrate Cache
        logging.info("System: Hydrating Game Channel Cache...")
        self.active_game_channels = await persistence.get_active_game_channels()
        
        # 2. Sync Slash Commands
        logging.info("System: Syncing Slash Commands...")
        await self.tree.sync()

# Initialize the Bot
client = ChickenBot()

# --- SLASH COMMANDS ---

@client.tree.command(name="cscratch", description="Boot a game cartridge")
@app_commands.describe(cartridge="The Story ID (default: hms-bucket)")
async def cscratch(interaction: discord.Interaction, cartridge: str = "hms-bucket"):
    await interaction.response.defer()

    try:
        # 1. Start Game
        game_id = await game_engine.start_new_game(story_id=cartridge)
        
        # 2. Build UI
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
        await interaction.followup.send(f"🐔 **Chicken Scratch Engine**\nLoading Cartridge: `{cartridge}`...\nID: `{game_id}`\nLocation: {channel.mention}")
        await channel.send("**HMS Bucket**\n*System Online. Waiting for input...*")
        
    except Exception as e:
        logging.error(f"Slash Command Error: {e}")
        await interaction.followup.send(f"❌ Failed to start game: {str(e)}")

@client.tree.command(name="end", description="End the current game session")
async def end(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        # 1. Validate Context
        game_data = await game_engine.find_game_by_channel(interaction.channel_id)
        if not game_data:
            await interaction.followup.send("⚠️ This channel is not part of an active game.")
            return

        await interaction.followup.send("🛑 **Ending Game...** Teardown sequence initiated.")
        
        # 2. Teardown UI
        interface = game_data.get('interface', {})
        cat_id = int(interface.get('category_id'))
        category = interaction.guild.get_channel(cat_id)
        
        if category:
            for channel in category.channels:
                await channel.delete()
            await category.delete()
        
        # 3. Mark Ended in DB
        await game_engine.end_game(game_data['id'])
        
        # 4. Clean Cache
        channel_id = interface.get('channel_id')
        if channel_id and str(channel_id) in client.active_game_channels:
            client.active_game_channels.remove(str(channel_id))

    except Exception as e:
        logging.error(f"Error in /end: {e}")
        pass

# --- GAMEPLAY LISTENER ---

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # THE FIREHOSE FILTER
    if str(message.channel.id) not in client.active_game_channels:
        return

    # IDEMPOTENCY
    if not await persistence.lock_event(message.id):
        return

    # GAME ENGINE
    try:
        async with message.channel.typing():
            response_text = await game_engine.process_player_input(
                channel_id=message.channel.id,
                user_input=message.content
            )
        
        if response_text:
            await message.channel.send(response_text)
            
    except Exception as e:
        logging.error(f"Gameplay Error: {e}")
