import logging
import discord
import asyncio
import aiohttp
import random
import string
from discord.ext import commands

from . import persistence
from . import presentation
from . import state
from .models import GameInterface
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
        logging.info(presentation.LOG_HYDRATING)
        self.active_game_channels = await persistence.db.get_active_game_channels()
        await self.tree.sync()

# --- HEADLESS REST INTERFACE (HTTP) ---
class DiscordRESTInterface:
    """
    Stateless Interface for the Gateway Architecture.
    Uses discord.py's HTTP capabilities without a WebSocket connection.
    """
    def __init__(self):
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

    # --- LOBBY CREATION ---
    
    async def create_lobby(self, game_id: str, cartridge: str, guild_id: str, host_id: str, origin_channel_id: str):
        try:
            # 1. Fetch full guild (includes roles) for correct permission evaluation
            guild = await self.client.fetch_guild(int(guild_id))
            origin_channel = await self.client.fetch_channel(int(origin_channel_id))
            
            # BYOC (Bring Your Own Category) Enforcment
            if not getattr(origin_channel, 'category_id', None):
                raise ValueError("NO_CATEGORY")
                
            # 2. Fetch channels BOUND to this hydrated guild so permissions map correctly
            channels = await guild.fetch_channels()
            category = next((c for c in channels if c.id == origin_channel.category_id), None)
            
            # Fallback direct fetch with manual guild bind if not found in list
            if not category:
                category = await self.client.fetch_channel(origin_channel.category_id)
                category.guild = guild
                
            bot_member = await guild.fetch_member(self.client.user.id)
            perms = category.permissions_for(bot_member)
            
            # 3. Dynamic Permission Check
            required_perms = {
                "View Channels": perms.read_messages,
                "Send Messages": perms.send_messages,
                "Manage Channels": perms.manage_channels,
                "Manage Roles (Permissions)": perms.manage_roles
            }
            
            missing = [name for name, has_perm in required_perms.items() if not has_perm]
            if missing:
                raise ValueError(f"MISSING_BOT_PERMS:{', '.join(missing)}")
                
            callsign = "".join(random.choices(string.ascii_uppercase, k=3))
            
            interface_data = {
                "type": "discord",
                "guild_id": guild_id,
                "category_id": str(origin_channel.category_id),
                "main_channel_id": str(origin_channel.id),
                "callsign": callsign,
                "listener_ids": [] # Don't listen to the dispatch channel
            }
            
            interface = GameInterface(**interface_data)
            await persistence.db.update_game_interface(game_id, interface)
            
            # NOTE: We specifically DO NOT register the origin (dispatch) channel into the persistence layer.
            # Interactions will rely on the embedded game_id in the button custom_ids.
            
            embed = discord.Embed(
                title=presentation.format_lobby_title(cartridge, callsign),
                description=presentation.LOBBY_DESC,
                color=0x00ff00
            )
            
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label=presentation.BTN_JOIN, style=discord.ButtonStyle.green, custom_id=f"join_btn_{game_id}"))
            view.add_item(discord.ui.Button(label=presentation.BTN_START, style=discord.ButtonStyle.danger, custom_id=f"start_btn_{game_id}"))
            
            await origin_channel.send(embed=embed, view=view)
            await origin_channel.send(presentation.MSG_LOBBY_INSTRUCTIONS)

            await self.check_and_warn_admin(guild_id, host_id, str(origin_channel.id))
        except ValueError as ve:
            raise ve
        except Exception as e:
            logging.error(f"Failed to create Discord lobby for {game_id}: {e}")
            raise e

    async def check_category_capacity(self, guild_id: str, category_id: str, needed_slots: int) -> bool:
        """Ensures the parent category won't hit the 50 channel limit."""
        if not guild_id or not category_id: return False
        try:
            guild = await self.client.fetch_guild(int(guild_id))
            channels = await guild.fetch_channels()
            count = sum(1 for c in channels if getattr(c, 'category_id', None) == int(category_id))
            return (count + needed_slots) <= 50
        except Exception as e:
            logging.error(f"Capacity check failed: {e}")
            return True # Fail open to prevent locking up if the API lags

    # --- OUTPUT METHODS ---

    async def announce_state(self, message: str):
        # Hardcoded debug channel from original code
        DEBUG_CHANNEL_ID = 1460557810545856725
        await self.send_message(DEBUG_CHANNEL_ID, presentation.format_announcement(message))

    async def send_message(self, channel_id: str, text: str):
        if not text: return
        try:
            channel = await self.client.fetch_channel(int(channel_id))
            if len(text) > 2000: text = text[:1990] + "..."
            await channel.send(text)
        except discord.NotFound:
            logging.warning(f"Channel {channel_id} not found (Orphaned Game?)")
        except Exception as e:
            logging.error(f"Send Error {channel_id}: {e}")

    async def delete_response(self, interaction_token: str, application_id: str):
        if not interaction_token or not application_id: return
        url = f"https://discord.com/api/v10/webhooks/{application_id}/{interaction_token}/messages/@original"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(url) as resp:
                    if resp.status >= 400:
                        logging.error(f"Delete Response Failed {resp.status}: {await resp.text()}")
        except Exception as e:
            logging.error(f"Delete Response Error: {e}")

    async def edit_response(self, interaction_token: str, application_id: str, text: str, clear_buttons: bool = False):
        if not interaction_token or not application_id: return
        url = f"https://discord.com/api/v10/webhooks/{application_id}/{interaction_token}/messages/@original"
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"content": text}
                if clear_buttons:
                    payload["components"] = []
                headers = {"Content-Type": "application/json"}
                
                async with session.patch(url, json=payload, headers=headers) as resp:
                    if resp.status >= 400:
                        logging.error(f"Edit Response Failed {resp.status}: {await resp.text()}")
        except Exception as e:
            logging.error(f"Edit Response Error: {e}")

    async def send_followup(self, interaction_token: str, application_id: str, text: str):
        if not interaction_token or not application_id: return
        url = f"https://discord.com/api/v10/webhooks/{application_id}/{interaction_token}"
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"content": text}
                headers = {"Content-Type": "application/json"}
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status >= 400:
                        logging.error(f"Followup Failed {resp.status}: {await resp.text()}")
        except Exception as e:
            logging.error(f"Followup Error: {e}")

    async def check_and_warn_admin(self, guild_id: str, user_id: str, channel_id: str):
        if not guild_id: return
        try:
            guild = await self.client.fetch_guild(int(guild_id))
            member = await guild.fetch_member(int(user_id))
            if member.guild_permissions.administrator:
                await self.send_message(channel_id, presentation.format_admin_warning(member.display_name))
        except Exception as e:
            logging.warning(f"Failed to perform admin check: {e}")

    async def unlock_channel(self, channel_id: str, guild_id: str):
        try:
            channel = await self.client.fetch_channel(int(channel_id))
            guild = await self.client.fetch_guild(int(guild_id))
            
            overwrite = channel.overwrites_for(guild.default_role)
            overwrite.read_messages = True
            await channel.set_permissions(guild.default_role, overwrite=overwrite)
            await channel.send(presentation.BLACK_BOX_OPEN)
        except Exception as e:
            logging.error(f"Unlock Failed: {e}")

    async def lock_channels(self, game_id: str, interface_data: dict):
        game = await persistence.db.get_game_by_id(game_id)
        if not game: return

        callsign = game.interface.callsign or "UNK"
        report = presentation.build_cost_report(
            game_id=game.id,
            callsign=callsign,
            input_tokens=game.usage_input_tokens,
            output_tokens=game.usage_output_tokens
        )
        await self.announce_state(report)

        # Show Button in Aux-Comm instead of Lobby Main (since Main is now shared dispatch)
        aux_chan_id = interface_data.get('channels', {}).get('aux-comm')
        if aux_chan_id:
            try:
                channel = await self.client.fetch_channel(int(aux_chan_id))
                lobby_name = presentation.format_lobby_title(game.story_id, callsign)
                embed = discord.Embed(
                    title=presentation.format_game_complete_title(lobby_name),
                    description=presentation.EMBED_DESC_ENDED,
                    color=0x992D22
                )
                view = discord.ui.View()
                btn = discord.ui.Button(
                    label=presentation.BTN_DELETE_CHANNELS, 
                    style=discord.ButtonStyle.danger, 
                    custom_id=f"end_delete_btn_{game_id}"
                )
                view.add_item(btn)
                await channel.send(embed=embed, view=view)
            except Exception as e:
                logging.error(f"Lock Channels Failed: {e}")

    async def execute_channel_ops(self, game_id: str, ops: list):
        if not ops: return
        game = await persistence.db.get_game_by_id(game_id)
        if not game or not game.interface.guild_id: return

        try:
            guild = await self.client.fetch_guild(int(game.interface.guild_id))
            try:
                bot_member = await guild.fetch_member(self.client.user.id)
            except Exception as e:
                logging.error(f"Failed to fetch bot member: {e}")
                return

            category = None
            if game.interface.category_id:
                try:
                    category = await self.client.fetch_channel(int(game.interface.category_id))
                except:
                    pass

            interface = game.interface
            changes = False
            callsign = interface.callsign or "UNK"

            for op in ops:
                if op['op'] == 'create':
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        bot_member: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                    }
                    if op.get('audience') == 'public':
                         overwrites[guild.default_role] = discord.PermissionOverwrite(read_messages=True)
                    elif op.get('audience') == 'private':
                        user_id = op.get('user_id')
                        if user_id:
                            try:
                                member = await guild.fetch_member(int(user_id))
                                overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                            except:
                                logging.warning(f"Member {user_id} not found for private channel")

                    # Prefix channel name with Callsign
                    raw_name = op.get('name', presentation.CHANNEL_UNKNOWN)
                    c_name = presentation.safe_channel_name(f"{callsign}-{raw_name}")
                    
                    new_chan = await guild.create_text_channel(c_name, category=category, overwrites=overwrites)
                    if op.get('init_msg'): await new_chan.send(op['init_msg'])
                    
                    key = op.get('key') 
                    if key: interface.channels[key] = str(new_chan.id)
                    if str(new_chan.id) not in interface.listener_ids:
                        interface.listener_ids.append(str(new_chan.id))
                    
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
        try:
            # We ONLY delete the generated game channels, NOT the main dispatch channel or category
            known_channels = list(interface_data.get('channels', {}).values())
            
            for cid in known_channels:
                if cid:
                    try:
                        c = await self.client.fetch_channel(int(cid))
                        await c.delete()
                        await persistence.db.remove_channel_association(cid)
                    except discord.NotFound:
                        pass
                    except Exception as e:
                        logging.warning(f"Failed to delete channel {cid}: {e}")
        except Exception as e:
            logging.error(f"Cleanup failed: {e}")


# Global Instance
client = DiscordRESTInterface()