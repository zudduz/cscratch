import logging
import discord
from discord import app_commands
from discord.ext import commands

from . import game_engine
from . import persistence
from .models import GameInterface

async def process_channel_ops(guild: discord.Guild, category: discord.CategoryChannel, ops: list, game_id: str):
    if not ops: return
    game = await persistence.db.get_game_by_id(game_id)
    if not game: return
    interface = game.interface
    changes_made = False

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
                
                client.active_game_channels.add(str(new_channel.id))
                changes_made = True
                
            elif op['op'] == 'delete':
                pass

        except Exception as e:
            logging.error(f"Channel Op Failed: {e}")

    if changes_made:
        await persistence.db.update_game_interface(game_id, interface)

class LobbyView(discord.ui.View):
    def __init__(self, game_id: str, cartridge_name: str):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.cartridge_name = cartridge_name

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.green, custom_id="join_btn")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await game_engine.join_game(self.game_id, str(interaction.user.id), interaction.user.name)
        await interaction.response.send_message(f"✅ **{interaction.user.name}** joined the squad!", ephemeral=False)

    @discord.ui.button(label="Start Match", style=discord.ButtonStyle.danger, custom_id="start_btn")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        result = await game_engine.launch_match(self.game_id)
        if not result:
             await interaction.followup.send("Error: Launch failed.")
             return

        ops = result.get('channel_ops', [])
        if ops:
            await interaction.followup.send("🏗️ **Configuring Ship Systems...**")
            category = interaction.channel.category
            await process_channel_ops(interaction.guild, category, ops, self.game_id)
        
        self.stop()
        await interaction.followup.send(f"🚨 **SIMULATION ACTIVE**")

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

client = ChickenBot()

cscratch_group = app_commands.Group(name="cscratch", description="Chicken Scratch Engine Controls")

@cscratch_group.command(name="start", description="Open a Game Lobby")
@app_commands.describe(cartridge="The Story ID (default: foster-protocol)")
async def start(interaction: discord.Interaction, cartridge: str = "foster-protocol"):
    await interaction.response.defer()

    try:
        # Pass Host Details
        game_id = await game_engine.start_new_game(
            story_id=cartridge,
            host_id=str(interaction.user.id),
            host_name=interaction.user.name
        )
        
        guild = interaction.guild
        category = await guild.create_category(f"Lobby {game_id}")
        channel = await guild.create_text_channel("pre-game-lobby", category=category)
        
        await game_engine.register_interface(game_id, {
            "type": "discord",
            "guild_id": str(guild.id),
            "category_id": str(category.id),
            "main_channel_id": str(channel.id),
            "listener_ids": [str(channel.id)]
        })
        client.active_game_channels.add(str(channel.id))
        
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
        game = await game_engine.find_game_by_channel(interaction.channel_id)
        if not game:
            await interaction.followup.send("⚠️ No active game here.")
            return

        await interaction.followup.send("🛑 **Teardown sequence initiated.**")
        
        cat_id = int(game.interface.category_id)
        category = interaction.guild.get_channel(cat_id)
        
        if category:
            for channel in category.channels: 
                await channel.delete()
                if str(channel.id) in client.active_game_channels:
                    client.active_game_channels.remove(str(channel.id))
            await category.delete()
        
        await game_engine.end_game(game.id)
        
    except Exception as e:
        logging.error(f"Error in /cscratch end: {e}")
        pass

@client.event
async def on_message(message):
    if message.author == client.user: return
    if str(message.channel.id) not in client.active_game_channels: return
    if not await persistence.db.lock_event(message.id): return

    try:
        async with message.channel.typing():
            response_payload = await game_engine.process_player_input_full(
                channel_id=message.channel.id,
                channel_name=message.channel.name,
                user_id=str(message.author.id),
                user_name=message.author.name,
                user_input=message.content
            )
        
        if isinstance(response_payload, dict):
            text = response_payload.get('response')
            ops = response_payload.get('channel_ops')
            
            if ops:
                category = message.channel.category
                game_id = response_payload.get('game_id') 
                if game_id:
                    await process_channel_ops(message.guild, category, ops, game_id)

            if text:
                await message.channel.send(text)
            
    except Exception as e:
        logging.error(f"Gameplay Error: {e}")
