import logging
import discord
from discord import app_commands
from discord.ext import commands

# Relative Imports
from . import game_engine
from . import persistence

# --- UI VIEW: THE LOBBY ---
class LobbyView(discord.ui.View):
    def __init__(self, game_id: str, cartridge_name: str):
        super().__init__(timeout=None) # Persistent view
        self.game_id = game_id
        self.cartridge_name = cartridge_name

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.green, custom_id="join_btn")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. Add Player to DB
        await game_engine.join_game(self.game_id, str(interaction.user.id), interaction.user.name)
        
        # 2. Update UI
        await interaction.response.send_message(f"✅ **{interaction.user.name}** joined the squad!", ephemeral=False)

    @discord.ui.button(label="Start Match", style=discord.ButtonStyle.danger, custom_id="start_btn")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. Transition State
        await game_engine.launch_match(self.game_id)
        
        # 2. Update UI
        self.stop() # Disable buttons
        await interaction.response.send_message("🚨 **MATCH LAUNCHING...** Preparing simulation...")
        
        # 3. Rename Channel (Optional visual flair)
        # await interaction.channel.edit(name="cryo-bay")
        
        await interaction.channel.send(f"**{self.cartridge_name}**\n*Sequence initiated. Good luck.*")

# --- BOT SETUP ---
class ChickenBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.active_game_channels = set()

    async def setup_hook(self):
        logging.info("System: Hydrating Game Channel Cache...")
        self.active_game_channels = await persistence.get_active_game_channels()
        self.tree.add_command(cscratch_group)
        logging.info("System: Syncing Slash Commands...")
        await self.tree.sync()

client = ChickenBot()

# --- COMMANDS ---
cscratch_group = app_commands.Group(name="cscratch", description="Chicken Scratch Engine Controls")

@cscratch_group.command(name="start", description="Open a Game Lobby")
@app_commands.describe(cartridge="The Story ID (default: foster-protocol)")
async def start(interaction: discord.Interaction, cartridge: str = "foster-protocol"):
    await interaction.response.defer()

    try:
        # 1. Create Game Record (Status: Setup)
        game_id = await game_engine.start_new_game(story_id=cartridge)
        
        # 2. Create Lobby Channel
        guild = interaction.guild
        category = await guild.create_category(f"Lobby {game_id}")
        channel = await guild.create_text_channel("pre-game-lobby", category=category)
        
        # 3. Register Interface
        await game_engine.register_interface(game_id, {
            "type": "discord",
            "guild_id": str(guild.id),
            "channel_id": str(channel.id),
            "category_id": str(category.id)
        })
        client.active_game_channels.add(str(channel.id))
        
        # 4. Send Lobby Interface
        embed = discord.Embed(title=f"Lobby: {cartridge}", description="Click below to join.", color=0x00ff00)
        embed.set_footer(text=f"Game ID: {game_id}")
        
        view = LobbyView(game_id=game_id, cartridge_name=cartridge)
        await channel.send(embed=embed, view=view)
        
        await interaction.followup.send(f"✅ Lobby Created: {channel.mention}")
        
    except Exception as e:
        logging.error(f"Slash Command Error: {e}")
        await interaction.followup.send(f"❌ Failed: {str(e)}")

@cscratch_group.command(name="end", description="Eject the cartridge and cleanup")
async def end(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        game_data = await game_engine.find_game_by_channel(interaction.channel_id)
        if not game_data:
            await interaction.followup.send("⚠️ No active game here.")
            return

        await interaction.followup.send("🛑 **Teardown sequence initiated.**")
        
        interface = game_data.get('interface', {})
        cat_id = int(interface.get('category_id'))
        category = interaction.guild.get_channel(cat_id)
        
        if category:
            for channel in category.channels: await channel.delete()
            await category.delete()
        
        await game_engine.end_game(game_data['id'])
        
        channel_id = interface.get('channel_id')
        if channel_id and str(channel_id) in client.active_game_channels:
            client.active_game_channels.remove(str(channel_id))

    except Exception as e:
        logging.error(f"Error in /cscratch end: {e}")
        pass

@client.event
async def on_message(message):
    if message.author == client.user: return
    if str(message.channel.id) not in client.active_game_channels: return
    if not await persistence.lock_event(message.id): return

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
