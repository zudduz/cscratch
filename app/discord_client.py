import logging
import discord
import asyncio
import os
from discord import app_commands
from discord.ext import commands

from . import game_engine
from . import persistence
from .state import sys as system_state

DEBUG_CHANNEL_ID = 1460557810545856725

async def safe_defer(interaction: discord.Interaction, ephemeral: bool = False) -> bool:
    if system_state.shutting_down: return False
    try:
        await interaction.response.defer(ephemeral=ephemeral)
        return True
    except discord.NotFound:
        logging.warning(f"Interaction {interaction.id} failed (10062). Race condition.")
        return False
    except discord.HTTPException as e:
        if e.code == 40060: return False
        raise e
    except discord.InteractionResponded:
        return False

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
        logging.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.announce_state("[ONLINE] **System Online**")

    async def announce_state(self, message: str):
        if not DEBUG_CHANNEL_ID: return
        try:
            rev = os.environ.get('K_REVISION', 'Local-Dev')
            channel = self.get_channel(DEBUG_CHANNEL_ID)
            if channel: await channel.send(f"{message}: `{rev}`")
        except Exception as e: logging.error(f"Announce failed: {e}")

    async def send_message(self, channel_id: str, text: str):
        try:
            channel = self.get_channel(int(channel_id))
            if not channel: return
            if len(text) > 2000: text = text[:1990] + "..."
            await channel.send(text)
        except Exception as e: logging.error(f"Discord Send Error {channel_id}: {e}")

    async def unlock_channel(self, channel_id: str, guild_id: str):
        try:
            guild = self.get_guild(int(guild_id))
            channel = guild.get_channel(int(channel_id))
            if not channel: return
            
            overwrite = channel.overwrites_for(guild.default_role)
            overwrite.read_messages = True
            await channel.set_permissions(guild.default_role, overwrite=overwrite)
            await channel.send("[OPEN] **BLACK BOX DECLASSIFIED. LOGS AVAILABLE.**")
        except Exception as e:
            logging.error(f"Unlock Failed: {e}")

    async def execute_channel_ops(self, game_id: str, ops: list):
        if not ops: return
        game = await persistence.db.get_game_by_id(game_id)
        if not game or not game.interface.guild_id: return
        guild = self.get_guild(int(game.interface.guild_id))
        if not guild: return
        
        category = None
        if game.interface.category_id:
            category = guild.get_channel(int(game.interface.category_id))

        changes = False
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
                    
                    elif op.get('audience') == 'hidden':
                        overwrites[guild.default_role] = discord.PermissionOverwrite(read_messages=False)
                        overwrites[guild.me] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

                    channel_name = op.get('name', 'unknown')
                    c_name = "".join(c for c in channel_name if c.isalnum() or c == "-").lower()
                    new_chan = await guild.create_text_channel(c_name, category=category, overwrites=overwrites)

                    if op.get('init_msg'): await new_chan.send(op['init_msg'])
                    key = op.get('key') 
                    if key: interface.channels[key] = str(new_chan.id)
                    if str(new_chan.id) not in interface.listener_ids:
                        interface.listener_ids.append(str(new_chan.id))
                    self.active_game_channels.add(str(new_chan.id))
                    changes = True
                    
                elif op['op'] == 'reveal':
                    key = op.get('key')
                    chan_id = interface.channels.get(key)
                    if chan_id:
                        await self.unlock_channel(chan_id, game.interface.guild_id)

            except Exception as e: logging.error(f"Op Failed: {e}")

        if changes: await persistence.db.update_game_interface(game_id, interface)

client = ChickenBot()

# --- COMMANDS ---
@app_commands.command(name="version", description="Check container")
async def version_cmd(interaction: discord.Interaction):
    rev = os.environ.get('K_REVISION', 'Local-Dev')
    await interaction.response.send_message(f"[NODE] **Active Node:** `{rev}`")

cscratch_group = app_commands.Group(name="cscratch", description="Engine Controls")

ADMIN_WARNING_TEXT = (
    "[WARNING] **FAIR PLAY NOTICE** [WARNING]\n"
    "To the Administrator: You have permissions to view ALL private channels.\n"
    "**FOR A FAIR GAME:** Please **MUTE** or **COLLAPSE** the private channels of other players.\n"
    "*The Protocol relies on trust.*"
)

@cscratch_group.command(name="start", description="Open Lobby")
async def start(interaction: discord.Interaction, cartridge: str = "foster-protocol"):
    if not await safe_defer(interaction): return
    try:
        game_id = await game_engine.engine.start_new_game(cartridge, str(interaction.user.id), interaction.user.name)
        guild = interaction.guild
        cat = await guild.create_category(f"Lobby {game_id}")
        chan = await guild.create_text_channel("cscratch-lobby", category=cat)
        
        await game_engine.engine.register_interface_data(game_id, {
            "type": "discord",
            "guild_id": str(guild.id),
            "category_id": str(cat.id),
            "main_channel_id": str(chan.id),
            "listener_ids": [str(chan.id)]
        })
        client.active_game_channels.add(str(chan.id))
        
        embed = discord.Embed(title=f"Lobby: {cartridge}", description="Click to join.", color=0x00ff00)
        view = LobbyView(game_id=game_id)
        await chan.send(embed=embed, view=view)
        
        if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator:
            await chan.send(ADMIN_WARNING_TEXT)

        await interaction.followup.send(f"[OK] Lobby: {chan.mention}")

    except Exception as e: await interaction.followup.send(f"[ERROR] Failed: {e}")

@cscratch_group.command(name="end", description="Cleanup")
async def end(interaction: discord.Interaction):
    if not await safe_defer(interaction): return
    game = await game_engine.engine.find_game_by_channel(interaction.channel_id)
    if not game: return await interaction.followup.send("[WARN] No game.")
    if str(interaction.user.id) != game.host_id: return await interaction.followup.send("[DENIED] Host only.")
    
    await interaction.followup.send("[STOP] **Teardown.**")
    if game.interface.category_id:
        try:
            cat = interaction.guild.get_channel(int(game.interface.category_id))
            if cat:
                for c in cat.channels: 
                    await c.delete()
                    if str(c.id) in client.active_game_channels: client.active_game_channels.remove(str(c.id))
                await cat.delete()
        except: pass
    await game_engine.engine.end_game(game.id)

class LobbyView(discord.ui.View):
    def __init__(self, game_id): super().__init__(timeout=None); self.game_id = game_id
    
    @discord.ui.button(label="Join", style=discord.ButtonStyle.green, custom_id="join_btn")
    async def join_button(self, interaction, button):
        if not await safe_defer(interaction): return
        try:
            await game_engine.engine.join_game(self.game_id, str(interaction.user.id), interaction.user.name)
            await interaction.followup.send(f"[OK] **{interaction.user.name}** joined!")
        except Exception as e: await interaction.followup.send(f"[ERROR] {e}", ephemeral=True)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.danger, custom_id="start_btn")
    async def start_button(self, interaction, button):
        if not await safe_defer(interaction): return
        game = await persistence.db.get_game_by_id(self.game_id)
        if not game or str(interaction.user.id) != game.host_id: return await interaction.followup.send("[DENIED] Host only.")
        
        res = await game_engine.engine.launch_match(self.game_id)
        if not res: return await interaction.followup.send("Error.")
        
        if res.get('channel_ops'): await client.execute_channel_ops(self.game_id, res['channel_ops'])
        await game_engine.engine.dispatch_immediate_result(self.game_id, res)
        self.stop()
        await interaction.followup.send(f"[STARTED] **SEQUENCE INITIATED**")
        
        updated_game = await persistence.db.get_game_by_id(self.game_id)
        aux_comm_id = updated_game.interface.channels.get('aux-comm')
        if aux_comm_id:
            await game_engine.engine.dispatch_input(
                aux_comm_id, 
                "SYSTEM", 
                "Mainframe", 
                "!exec_wakeup_protocol"
            )

@client.event
async def on_message(message):
    if system_state.shutting_down: return
    if message.author == client.user: return
    if str(message.channel.id) not in client.active_game_channels: return
    if not await persistence.db.lock_event(message.id): return
    try:
        await game_engine.engine.dispatch_input(str(message.channel.id), str(message.author.id), message.author.name, message.content)
    except Exception as e: logging.error(f"Input Error: {e}")
