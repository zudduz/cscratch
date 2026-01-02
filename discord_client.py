import logging
import discord

# Import Domain & Data Layers
import game_engine
import persistence

# --- Discord Client Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

client = discord.Client(intents=intents)

# --- Events ---
@client.event
async def on_ready():
    logging.info(f'Discord Bot Connected: We have logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # IDEMPOTENCY CHECK (via Persistence Layer)
    if message.content.startswith('!'):
        if not await persistence.lock_event(message.id):
            return

    # Basic Ping
    if message.content.startswith('!ping'):
        await message.channel.send('Pong! (Hello from Cloud Run)')

    # --- COMMAND: INFO ---
    if message.content == '!info':
        try:
            game_data = await game_engine.find__by_channel(message.channel.id)

            if game_data:
                embed = discord.Embed(title=f"Game: {game_data.get('id')}", color=0x00ff00)
                embed.add_field(name="Status", value=game_data.get('status', 'Unknown'))
                embed.add_field(name="Story Engine", value=game_data.get('story_id', 'N/A'))
                embed.add_field(name="Created", value=str(game_data.get('created_at', 'Unknown')))
                await message.channel.send(embed=embed)
            else:
                await message.channel.send("ℹ️ This channel is not attached to any active game.")

        except Exception as e:
            logging.error(f"Error in !info command: {e}")
            await message.channel.send(f"❌ Error fetching info: {str(e)}")

    # --- COMMAND: START GAME ---
    if message.content == '!start':
        try:
            game_id = await game_engine.start_new_game(story_id="sleeping-agent")
            
            guild = message.guild
            category = await guild.create_category(f"Game {game_id}")
            channel = await guild.create_text_channel("adventure", category=category)
            
            await game_engine.register_interface(game_id, {
                "type": "discord",
                "guild_id": str(guild.id),
                "channel_id": str(channel.id),
                "category_id": str(category.id)
            })

            await message.channel.send(f"🚀 **Game Started!**\nID: `{game_id}`\nLocation: {channel.mention}")
            await channel.send(f"Welcome to Game `{game_id}`! The adventure begins here...")

        except Exception as e:
            logging.error(f"Error in !start command: {e}")
            await message.channel.send(f"❌ Error starting game: {str(e)}")

    # --- COMMAND: END GAME ---
    if message.content == '!end':
        try:
            game_data = await game_engine.find_game_by_channel(message.channel.id)
            if not game_data:
                await message.channel.send("⚠️ This channel is not part of an active game.")
                return

            await message.channel.send("🛑 **Ending Game...** Teardown sequence initiated.")
            
            # Teardown Discord UI
            interface = game_data.get('interface', {})
            category_id = int(interface.get('category_id'))
            category = message.guild.get_channel(category_id)
            
            if category:
                for channel in category.channels:
                    await channel.delete()
                await category.delete()
            
            await game_engine.end_game(game_data['id'])

        except Exception as e:
            logging.error(f"Error in !end command: {e}")

    # Command: Nuke (Cleanup Tool)
    if message.content.startswith('!nuke '):
        try:
            target_name = message.content.split(' ')[1]
            guild = message.guild
            deleted_count = 0

            for channel in guild.channels:
                if target_name in channel.name:
                    await channel.delete()
                    deleted_count += 1
            
            if deleted_count > 0:
                await message.channel.send(f"☢️ Nuked {deleted_count} channels/categories matching '{target_name}'")
            else:
                await message.channel.send(f"⚠️ No channels found matching '{target_name}'")

        except Exception as e:
            logging.error(f"Error in !nuke command: {e}")
            await message.channel.send(f"❌ Error nuking: {str(e)}")