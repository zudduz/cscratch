import logging
import discord
import asyncio
from discord import app_commands
from discord.ext import commands

from . import game_engine
from . import persistence

# --- HELPER: SAFE DEFER ---
async def safe_defer(interaction: discord.Interaction, ephemeral: bool = False) -> bool:
    try:
        await interaction.response.defer(ephemeral=ephemeral)
        return True
    except discord.HTTPException as e:
        if e.code == 40060: # Interaction already acknowledged
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
        logging.info("System: Syncing Slash Commands...")
        await self.tree.sync()
        
        await game_engine.engine.register_interface(self)
        await game_engine.engine.start()

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
        if not game or not game.interface.guild_id: 
            return

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

                    new_channel = await guild.create_text_channel(
                        channel_name, 
                        category=category, 
                        overwrites=overwrites
                    )

                    if op.get('init_msg'):
                        await new_channel.send(op['init_msg'])

                    key = op.get('key') 
                    if key:
                        interface.channels[key] = str(new_channel.id)
                    
                    if str(new_channel.id) not in interface.listener_ids:
                        interface.listener_ids.append(str(new_channel.id))
                    
                    self.active_game_channels.add(str(new_channel.id))
                    changes_made = True
                    
                elif op['op'] == 'delete':
                    pass 

            except Exception as e:
                logging.error(f"Channel Op Failed: {e}")

        if changes_made:
            await persistence.db.update_game_interface(game_id, interface)

client = ChickenBot()

# --- UI VIEWS ---

class LobbyView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.green, custom_id="join_btn")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await safe_defer(interaction): return

        try:
            # CALL THE ENGINE INSTANCE
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

        # CALL THE ENGINE INSTANCE
        game = await persistence.db.get_game_by_id(self.game_id)
        if not game:
            await interaction.followup.send("❌ Game not found.")
            return

        if str(interaction.user.id) != game.host_id:
            await interaction.followup.send(f"⛔ **Access Denied.** Only the Host (<@{game.host_id}>) can start the simulation.")
            return
        
        # CALL THE ENGINE INSTANCE
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


# --- SLASH COMMANDS ---

cscratch_group = app_commands.Group(name="cscratch", description="Chicken Scratch Engine Controls")

@cscratch_group.command(name="start", description="Open a Game Lobby")
@app_commands.describe(cartridge="The Story ID (default: foster-protocol)")
async def start(interaction: discord.Interaction, cartridge: str = "foster-protocol"):
    if not await safe_defer(interaction): return

    try:
        # CALL THE ENGINE INSTANCE
        game_id = await game_engine.engine.start_new_game(
            story_id=cartridge,
            host_id=str(interaction.user.id),
            host_name=interaction.user.name
        )
        
        guild = interaction.guild
        category = await guild.create_category(f"Lobby {game_id}")
        channel = await guild.create_text_channel("cscratch-lobby", category=category)
        
        # Register basic interface info - Engine call
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

    # CALL THE ENGINE INSTANCE
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
        
        # CALL THE ENGINE INSTANCE
        await game_engine.engine.end_game(game.id)
        
    except Exception as e:
        logging.error(f"Error in /cscratch end: {e}")

@client.event
async def on_message(message):
    if message.author == client.user: return
    if str(message.channel.id) not in client.active_game_channels: return
    if not await persistence.db.lock_event(message.id): return

    try:
        async with message.channel.typing():
            # CALL THE ENGINE INSTANCE
            await game_engine.engine.dispatch_input(
                channel_id=str(message.channel.id),
                user_id=str(message.author.id),
                user_name=message.author.name,
                user_input=message.content
            )
            
    except Exception as e:
        logging.error(f"Input Dispatch Error: {e}")
