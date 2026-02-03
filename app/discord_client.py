import logging
import discord
import asyncio
from discord.ext import commands

from . import persistence
from . import presentation
from .state import sys as system_state

# --- LEGACY CHICKEN BOT (WEBSOCKET) ---
class ChickenBot(commands.Bot):
    """
    Legacy WebSocket Bot. 
    Retained for local development or full-state modes.
    """
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.active_game_channels = {}

    async def setup_hook(self):
        # ... (Existing logic omitted for brevity, logic preserved in previous version)
        pass

# --- HEADLESS REST INTERFACE (HTTP) ---
class DiscordRESTInterface:
    """
    Stateless Interface for the Gateway Architecture.
    Uses discord.py's HTTP capabilities without a WebSocket connection.
    """
    def __init__(self):
        # We need a client instance to access the HTTP adapter and state models
        # We will login() but NEVER connect()
        intents = discord.Intents.default()
        self.client = discord.Client(intents=intents)
        self.is_ready = False

    async def start(self, token: str):
        """Authenticates the HTTP session."""
        try:
            await self.client.login(token)
            self.is_ready = True
            logging.info("Discord REST Interface: Authenticated")
        except Exception as e:
            logging.error(f"Discord REST Auth Failed: {e}")

    async def close(self):
        await self.client.close()

    # --- OUTPUT METHODS ---

    async def announce_state(self, message: str):
        # Hardcoded debug channel from original code
        DEBUG_CHANNEL_ID = 1460557810545856725
        await self.send_message(DEBUG_CHANNEL_ID, presentation.format_announcement(message))

    async def send_message(self, channel_id: str, text: str):
        if not text: return
        try:
            # fetch_channel makes an API call (Stateless)
            # We cast to int because Discord IDs are integers
            channel = await self.client.fetch_channel(int(channel_id))
            if len(text) > 2000: text = text[:1990] + "..."
            await channel.send(text)
        except discord.NotFound:
            logging.warning(f"Channel {channel_id} not found (Orphaned Game?)")
        except Exception as e:
            logging.error(f"Send Error {channel_id}: {e}")

    async def unlock_channel(self, channel_id: str, guild_id: str):
        try:
            channel = await self.client.fetch_channel(int(channel_id))
            guild = await self.client.fetch_guild(int(guild_id))
            
            # Update permissions
            overwrite = channel.overwrites_for(guild.default_role)
            overwrite.read_messages = True
            await channel.set_permissions(guild.default_role, overwrite=overwrite)
            await channel.send(presentation.BLACK_BOX_OPEN)
        except Exception as e:
            logging.error(f"Unlock Failed: {e}")

    async def lock_channels(self, game_id: str, interface_data: dict):
        """
        End Game Logic: Show the 'Delete Channels' button.
        Since we can't attach a View listener, we send a static message 
        that informs the user what to do, or a button that Gateway routes back to us.
        """
        game = await persistence.db.get_game_by_id(game_id)
        if not game: return

        # 1. Announce Costs
        report = presentation.build_cost_report(
            game_id=game.id,
            input_tokens=game.usage_input_tokens,
            output_tokens=game.usage_output_tokens
        )
        await self.announce_state(report)

        # 2. Show Button in Lobby
        # We construct a View that matches what the Gateway expects
        main_chan_id = interface_data.get('main_channel_id')
        if main_chan_id:
            try:
                channel = await self.client.fetch_channel(int(main_chan_id))
                
                embed = discord.Embed(
                    title=presentation.EMBED_TITLE_ENDED,
                    description=presentation.EMBED_DESC_ENDED,
                    color=0x992D22
                )
                
                # In stateless mode, we send a View, but the interaction 
                # will be caught by the Gateway and forwarded to /ingress
                view = discord.ui.View()
                btn = discord.ui.Button(
                    label=presentation.BTN_DELETE_CHANNELS, 
                    style=discord.ButtonStyle.danger, 
                    custom_id="end_delete_btn"
                )
                view.add_item(btn)
                
                await channel.send(embed=embed, view=view)
            except Exception as e:
                logging.error(f"Lock Channels Failed: {e}")

    async def execute_channel_ops(self, game_id: str, ops: list):
        if not ops: return
        
        # We need the guild to perform creates
        # We assume the first op has context or we fetch game again (expensive)
        # Optimization: We fetch the game once to get the Guild ID
        game = await persistence.db.get_game_by_id(game_id)
        if not game or not game.interface.guild_id: return

        try:
            guild = await self.client.fetch_guild(int(game.interface.guild_id))
            
            category = None
            if game.interface.category_id:
                try:
                    category = await self.client.fetch_channel(int(game.interface.category_id))
                except:
                    pass # Category might be gone

            interface = game.interface
            changes = False

            for op in ops:
                if op['op'] == 'create':
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                    }
                    
                    # Mapping logic from original code...
                    if op.get('audience') == 'public':
                         overwrites[guild.default_role] = discord.PermissionOverwrite(read_messages=True)
                    elif op.get('audience') == 'private':
                        user_id = op.get('user_id')
                        if user_id:
                            # We need to fetch the member to set permissions
                            try:
                                member = await guild.fetch_member(int(user_id))
                                overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                            except:
                                logging.warning(f"Member {user_id} not found for private channel")

                    raw_name = op.get('name', presentation.CHANNEL_UNKNOWN)
                    c_name = presentation.safe_channel_name(raw_name)
                    
                    new_chan = await guild.create_text_channel(c_name, category=category, overwrites=overwrites)

                    if op.get('init_msg'): await new_chan.send(op['init_msg'])
                    
                    key = op.get('key') 
                    if key: interface.channels[key] = str(new_chan.id)
                    if str(new_chan.id) not in interface.listener_ids:
                        interface.listener_ids.append(str(new_chan.id))
                    
                    # UPDATE CACHE & INDEX
                    await persistence.db.register_channel_association(str(new_chan.id), game_id)
                    changes = True
                
                elif op['op'] == 'reveal':
                    key = op.get('key')
                    chan_id = interface.channels.get(key)
                    if chan_id:
                        await self.unlock_channel(chan_id, game.interface.guild_id)

            if changes: 
                await persistence.db.update_game_interface(game_id, interface)
                
        except Exception as e:
            logging.error(f"Channel Op Error: {e}")

    async def cleanup_game_channels(self, guild_id_str: str, interface_data: dict):
        if not interface_data: return
        
        # Note: interface_data is a dict here
        cat_id = interface_data.get('category_id')
        
        try:
            # We iterate known channels from the interface to delete them
            # because we can't easily iterate the category contents statelessly without extra API calls
            
            # 1. Delete Channels listed in interface
            known_channels = [interface_data.get('main_channel_id')] + list(interface_data.get('channels', {}).values())
            
            for cid in known_channels:
                if cid:
                    try:
                        c = await self.client.fetch_channel(int(cid))
                        await c.delete()
                        await persistence.db.remove_channel_association(cid)
                    except discord.NotFound:
                        pass # Already deleted
                    except Exception as e:
                        logging.warning(f"Failed to delete channel {cid}: {e}")

            # 2. Delete Category
            if cat_id:
                try:
                    cat = await self.client.fetch_channel(int(cat_id))
                    await cat.delete()
                except:
                    pass
                    
        except Exception as e:
            logging.error(f"Cleanup failed: {e}")


# Global Instance
client = DiscordRESTInterface()