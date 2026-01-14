import logging
import discord
import asyncio
import os
from discord import app_commands
from discord.ext import commands

from . import game_engine
from . import persistence
from .state import sys as system_state

# --- CONFIGURATION ---
DEBUG_CHANNEL_ID = 1460557810545856725

# --- HELPER: SAFE DEFER ---
async def safe_defer(interaction: discord.Interaction, ephemeral: bool = False) -> bool:
    # 1. Check Global Shutdown Flag
    if system_state.shutting_down: 
        return False
        
    try:
        await interaction.response.defer(ephemeral=ephemeral)
        return True
        
    except discord.NotFound:
        # Error 10062: Unknown interaction. 
        # This usually means another bot instance handled it first, 
        # or the token expired before we got here.
        logging.warning(f"Interaction {interaction.id} failed (10062: Unknown). Race condition loser.")
        return False
        
    except discord.HTTPException as e:
        if e.code == 40060: 
            logging.warning(f"Race Condition: Interaction {interaction.id} handled by another bot instance.")
            return False
        raise e
        
    except discord.InteractionResponded:
        return False

# --- THE DUMB TERMINAL ---

class ChickenBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.active_game_channels = set()

    async def setup_hook(self):
        logging.info("System: Hydrating Game Channel Cache...")
        self.active_game_channels = await persistence.db.get_active_game_channels()
        
        self.tree.add_command(cscratch_group)
        self.tree.add_command(version_cmd)
        
        logging.info("System: Syncing Slash Commands...")
        await self.tree.sync()
        
        await game_engine.engine.register_interface(self)
        await game_engine.engine.start()

    async def on_ready(self):
        """Called when the bot connects to Discord."""
        logging.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.announce_state("🟢 **System Online**")

    async def announce_state(self, message: str):
        """Helper to send debug messages to the admin channel."""
        if not DEBUG_CHANNEL_ID: return
        
        try:
            # Determine Revision
            rev = os.environ.get('K_REVISION', 'Local-Dev')
            
            # Find Channel (ID is int)
            channel = self.get_channel(DEBUG_CHANNEL_ID)
            if channel:
                await channel.send(f"{message}: `{rev}`")
        except Exception as e:
            logging.error(f"Failed to send announcement: {e}")

    async def send_message(self, channel_id: str, text: str):
        try:
            channel = self.get_channel(int(channel_id))
            if channel:
                await channel.send(text)
            else:
                logging.warning(f"Discord Interface: Channel {channel_id} not found/cached.")
        except Exception as e:
            logging.error(f"Discord Interface Error sending to {channel_id}: {e}")

    async def execute_channel_ops(self, game_id: str, ops: list):
        if not ops: return
        
        game = await persistence.db.get_game_by_id(game_id)
        if not game or not game.interface.guild_id: return

        guild = self.get_guild(int(game.interface.guild_id))
        if not guild: return
        
        category = None
        if game.interface.category_id:
            category = guild.get_channel(int(game.interface.category_id))

        changes_made = False
        interface = game.interface

        for op in ops:
            try:
                if op['op'] == 'create':
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                    }
                    if op.get('audience') == 'public':
                         overwrites[guild.default_role] = discord.PermissionOverwrite(read_messages=True)
                    elif op.get('audience') == 'private':
                        user_id = op.get('user_id')
                        if user_id:
                            member = guild.get_member(int(user_id))
                            if member:
                                overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

                    channel_name = op.get('name', 'unknown-channel')
                    channel_name = "".join(c for c in channel_name if c.isalnum() or c == "-").lower()

                    new_channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

                    if op.get('init_msg'): await new_channel.send(op['init_msg'])

                    key = op.get('key') 
                    if key: interface.channels[key] = str(new_channel.id)
                    
                    if str(new_channel.id) not in interface.listener_ids:
                        interface.listener_ids.append(str(new_channel.id))
                    
                    self.active_game_channels.add(str(new_channel.id))
                    changes_made = True
                    
                elif op['op'] == 'delete': pass 

            except Exception as e:
                logging.error(f"Channel Op Failed: {e}")

        if changes_made:
            await persistence.db.update_game_interface(game_id, interface)

    async def lock_channels(self, game_id: str, interface_data: dict):
        """Makes all game channels read-only except for the Lobby."""
        try:
            lobby_id = interface_data.get('main_channel_id')
            listener_ids = interface_data.get('listener_ids', [])
            
            for channel_id in listener_ids:
                if channel_id == lobby_id: continue # Skip lobby
                
                channel = self.get_channel(int(channel_id))
                if not channel: continue

                # Disable sending for existing overwrites
                for target in channel.overwrites:
                    if target == self.user or target == channel.guild.me: continue
                    
                    overwrites = channel.overwrites[target]
                    overwrites.send_messages = False
                    await channel.set_permissions(target, overwrite=overwrites)
                    
            logging.info(f"Game {game_id} channels locked.")
        except Exception as e:
            logging.error(f"Lockdown Failed: {e}")

client = ChickenBot()

# --- COMMANDS ---

@app_commands.command(name="version", description="Check which container is serving you")
async def version_cmd(interaction: discord.Interaction):
    rev = os.environ.get('K_REVISION', 'Local-Dev')
    await interaction.response.send_message(f"🤖 **Active Node:** `{rev}`")

cscratch_group = app_commands.Group(name="cscratch", description="Chicken Scratch Engine Controls")

@cscratch_group.command(name="start", description="Open a Game Lobby")
@app_commands.describe(cartridge="The Story ID (default: foster-protocol)")
async def start(interaction: discord.Interaction, cartridge: str = "foster-protocol"):
    if not await safe_defer(interaction): return

    try:
        game_id = await game_engine.engine.start_new_game(
            story_id=cartridge,
            host_id=str(interaction.user.id),
            host_name=interaction.user.name
        )
        
        guild = interaction.guild
        category = await guild.create_category(f"Lobby {game_id}")
        channel = await guild.create_text_channel("cscratch-lobby", category=category)
        
        await game_engine.engine.register_interface_data(game_id, {
            "type": "discord",
            "guild_id": str(guild.id),
            "category_id": str(category.id),
            "main_channel_id": str(channel.id),
            "listener_ids": [str(channel.id)]
        })
        client.active_game_channels.add(str(channel.id))
        
        embed = discord.Embed(title=f"Lobby: {cartridge}", description="Click below to join.", color=0x00ff00)
        embed.set_footer(text=f"Game ID: {game_id}")
        
        view = LobbyView(game_id=game_id)
        await channel.send(embed=embed, view=view)
        
        await interaction.followup.send(f"✅ Lobby Created: {channel.mention}")
        
    except Exception as e:
        logging.error(f"Slash Command Error: {e}")
        await interaction.followup.send(f"❌ Failed: {str(e)}")

@cscratch_group.command(name="end", description="Eject the cartridge and cleanup")
async def end(interaction: discord.Interaction):
    if not await safe_defer(interaction): return

    game = await game_engine.engine.find_game_by_channel(interaction.channel_id)
    if not game:
        await interaction.followup.send("⚠️ No active game here.")
        return

    if str(interaction.channel_id) != game.interface.main_channel_id:
        await interaction.followup.send(f"⛔ System commands must be run from the Main Console (<#{game.interface.main_channel_id}>).")
        return

    if str(interaction.user.id) != game.host_id:
        await interaction.followup.send("⛔ **Access Denied.** Only the Host can terminate the simulation.")
        return

    try:
        await interaction.followup.send("🛑 **Teardown sequence initiated.**")
        
        if game.interface.category_id:
            try:
                category = interaction.guild.get_channel(int(game.interface.category_id))
                if category:
                    for channel in category.channels: 
                        await channel.delete()
                        if str(channel.id) in client.active_game_channels:
                            client.active_game_channels.remove(str(channel.id))
                    await category.delete()
            except Exception:
                pass
        
        await game_engine.engine.end_game(game.id)
        
    except Exception as e:
        logging.error(f"Error in /cscratch end: {e}")

class LobbyView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.green, custom_id="join_btn")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await safe_defer(interaction): return

        try:
            await game_engine.engine.join_game(self.game_id, str(interaction.user.id), interaction.user.name)
            await interaction.followup.send(f"✅ **{interaction.user.name}** joined the squad!")

            if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator:
                warning = (
                    f"⚠️ **FAIR PLAY ALERT:** {interaction.user.mention} has **Administrator Privileges**.\n"
                    "This allows them to see **ALL** private channels.\n"
                    "*The Protocol relies on trust.*"
                )
                await interaction.channel.send(warning)
        except Exception as e:
            logging.error(f"Join Error: {e}")
            await interaction.followup.send(f"❌ Failed to join: {str(e)}", ephemeral=True)

    @discord.ui.button(label="Start Match", style=discord.ButtonStyle.danger, custom_id="start_btn")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await safe_defer(interaction): return

        game = await persistence.db.get_game_by_id(self.game_id)
        if not game:
            await interaction.followup.send("❌ Game not found.")
            return

        if str(interaction.user.id) != game.host_id:
            await interaction.followup.send(f"⛔ **Access Denied.** Only the Host (<@{game.host_id}>) can start the simulation.")
            return
        
        result = await game_engine.engine.launch_match(self.game_id)
        if not result:
             await interaction.followup.send("Error: Launch failed.")
             return

        ops = result.get('channel_ops', [])
        if ops:
            await interaction.followup.send("🏗️ **Configuring Ship Systems...**")
            await client.execute_channel_ops(self.game_id, ops)
        
        await game_engine.engine.dispatch_immediate_result(self.game_id, result)
        self.stop()
        await interaction.followup.send(f"🚨 **SIMULATION ACTIVE**")

@client.event
async def on_message(message):
    # 1. SHUTDOWN GATEKEEPER
    if system_state.shutting_down: 
        return

    if message.author == client.user: return
    if str(message.channel.id) not in client.active_game_channels: return
    if not await persistence.db.lock_event(message.id): return

    try:
        async with message.channel.typing():
            await game_engine.engine.dispatch_input(
                channel_id=str(message.channel.id),
                user_id=str(message.author.id),
                user_name=message.author.name,
                user_input=message.content
            )
            
    except Exception as e:
        logging.error(f"Input Dispatch Error: {e}")
