import logging
import discord
import asyncio
import os
from discord import app_commands
from discord.ext import commands

from . import game_engine
from . import persistence
from .state import sys as system_state
from . import presentation

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
        self.active_game_channels = {}

    async def setup_hook(self):
        logging.info(presentation.LOG_HYDRATING)
        # Load the cache map from active games
        self.active_game_channels = await persistence.db.get_active_game_channels()
        self.tree.add_command(cscratch_group)
        self.tree.add_command(version_cmd)
        logging.info(presentation.LOG_SYNCING)
        await self.tree.sync()
        await game_engine.engine.register_interface(self)
        await game_engine.engine.start()

    async def on_ready(self):
        logging.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.announce_state(presentation.SYSTEM_ONLINE)

    async def announce_state(self, message: str):
        if not DEBUG_CHANNEL_ID: return
        try:
            channel = self.get_channel(DEBUG_CHANNEL_ID)
            text = presentation.format_announcement(message)
            if channel:
                 await channel.send(text)
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
            await channel.send(presentation.BLACK_BOX_OPEN)
        except Exception as e:
            logging.error(f"Unlock Failed: {e}")

    async def execute_channel_ops(self, game_id: str, ops: list):
        if not ops:
           return
        game = await persistence.db.get_game_by_id(game_id)
        if not game or not game.interface.guild_id:
            return
        guild = self.get_guild(int(game.interface.guild_id))
        if not guild:
            return
        
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

                    # Use presentation logic for safe naming
                    raw_name = op.get('name', presentation.CHANNEL_UNKNOWN)
                    c_name = presentation.safe_channel_name(raw_name)
                    
                    new_chan = await guild.create_text_channel(c_name, category=category, overwrites=overwrites)

                    if op.get('init_msg'): await new_chan.send(op['init_msg'])
                    key = op.get('key') 
                    if key: interface.channels[key] = str(new_chan.id)
                    if str(new_chan.id) not in interface.listener_ids:
                        interface.listener_ids.append(str(new_chan.id))
                    
                    # UPDATE CACHE & INDEX
                    self.active_game_channels[str(new_chan.id)] = game_id
                    await persistence.db.register_channel_association(str(new_chan.id), game_id)
                    
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
@app_commands.command(name="version", description=presentation.CMD_VERSION_DESC)
async def version_cmd(interaction: discord.Interaction):
    rev = os.environ.get('K_REVISION', 'Local-Dev')
    await interaction.response.send_message(presentation.format_version_response(rev))

cscratch_group = app_commands.Group(name="cscratch", description=presentation.CMD_GRP_SCRATCH)

@cscratch_group.command(name="start", description=presentation.CMD_START_DESC)
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
        
        # UPDATE CACHE & INDEX (Lobby Channel)
        client.active_game_channels[str(chan.id)] = game_id
        await persistence.db.register_channel_association(str(chan.id), game_id)
        
        embed = discord.Embed(
            title=presentation.format_lobby_title(cartridge),
            description=presentation.LOBBY_DESC,
            color=0x00ff00
        )
        view = LobbyView(game_id=game_id)
        await chan.send(embed=embed, view=view)
        
        if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator:
            await chan.send(presentation.ADMIN_WARNING)

        await interaction.followup.send(presentation.format_lobby_created_msg(chan.mention))

    except Exception as e:
        await interaction.followup.send(presentation.CMD_FAILED.format(error=e))

@cscratch_group.command(name="end", description=presentation.CMD_END_DESC)
async def end(interaction: discord.Interaction):
    if not await safe_defer(interaction):
        return
    game = await game_engine.engine.find_game_by_channel(interaction.channel_id)
    if not game:
        return await interaction.followup.send(presentation.ERR_NO_GAME)
    if str(interaction.user.id) != game.host_id:
        return await interaction.followup.send(presentation.ERR_NOT_HOST)
    
    await interaction.followup.send(presentation.MSG_TEARDOWN)
    
    # Use presentation logic for cost reporting
    report = presentation.build_cost_report(
        game_id=game.id,
        input_tokens=game.usage_input_tokens,
        output_tokens=game.usage_output_tokens
    )

    await client.announce_state(report)
    
    if game.interface.category_id:
        try:
            cat = interaction.guild.get_channel(int(game.interface.category_id))
            if cat:
                for c in cat.channels: 
                    await c.delete()
                    cid = str(c.id)
                    # CLEANUP CACHE & INDEX
                    if cid in client.active_game_channels: 
                        del client.active_game_channels[cid]
                    await persistence.db.remove_channel_association(cid)
                await cat.delete()
        except: pass
    await game_engine.engine.end_game(game.id)

class LobbyView(discord.ui.View):
    def __init__(self, game_id): super().__init__(timeout=None); self.game_id = game_id
    
    @discord.ui.button(label=presentation.BTN_JOIN, style=discord.ButtonStyle.green, custom_id="join_btn")
    async def join_button(self, interaction, button):
        if not await safe_defer(interaction): return
        try:
            await game_engine.engine.join_game(self.game_id, str(interaction.user.id), interaction.user.name)
            await interaction.followup.send(presentation.format_player_joined(interaction.user.name))
            if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator:
                await interaction.channel.send(presentation.ADMIN_WARNING)
        except Exception as e: await interaction.followup.send(f"Error {e}", ephemeral=True)

    @discord.ui.button(label=presentation.BTN_START, style=discord.ButtonStyle.danger, custom_id="start_btn")
    async def start_button(self, interaction, button):
        if not await safe_defer(interaction):
            return

        game = await persistence.db.get_game_by_id(self.game_id)
        if not game or str(interaction.user.id) != game.host_id:
            return await interaction.followup.send(presentation.ERR_NOT_HOST_START)
        
        # 1. Start game and get initial metadata/messages
        res = await game_engine.engine.launch_match(self.game_id)
        if not res:
            return await interaction.followup.send(presentation.ERR_GENERIC)
        
        # 2. CREATE CHANNELS (Ops)
        if res.get('channel_ops'):
            await client.execute_channel_ops(self.game_id, res['channel_ops'])

        # 3. Send immediate messages (Intro messages)
        await game_engine.engine.dispatch_immediate_result(self.game_id, res)
        self.stop()
        await interaction.followup.send(presentation.MSG_STARTING)
        
        # 4. LIFECYCLE HOOK: Post-Start
        # Channels exist, messages sent. Now we trigger the "Wake Up Protocol" logic.
        await game_engine.engine.trigger_post_start(self.game_id)

@client.event
async def on_message(message):
    if system_state.shutting_down:
        return
    if message.author == client.user:
        return
    if not await persistence.db.lock_event(message.id):
        return
    
    channel_id = str(message.channel.id)
    
    game_id = client.active_game_channels.get(channel_id)
    if not game_id:
        game_id = await persistence.db.get_game_id_by_channel_index(channel_id)
        if game_id:
            client.active_game_channels[channel_id] = game_id
            
    if not game_id:
        return

    try:
        await game_engine.engine.dispatch_input(channel_id, str(message.author.id), message.author.name, message.content, known_game_id=game_id)
    except Exception as e: logging.error(f"Input Error: {e}")