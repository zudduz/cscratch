import logging
import discord
import os

from . import game_engine
from . import persistence

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    logging.info(f'Discord Bot Connected: We have logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # 1. IDEMPOTENCY
    if message.content.startswith('!'):
        if not await persistence.lock_event(message.id):
            return

    # 2. COMMANDS
    if message.content.startswith('!ping'):
        await message.channel.send('Pong!')
        return

    if message.content.startswith('!list'):
        cartridges = [d for d in os.listdir('cartridges') if os.path.isdir(os.path.join('cartridges', d))]
        await message.channel.send(f"Available stories: {', '.join(cartridges)}")
        return

    if message.content.startswith('!start'):
        try:
            args = message.content.split()
            if len(args) < 2:
                await message.channel.send("❌ Please provide a story ID. Usage: `!start <story_id>`")
                return
            story_id = args[1]

            game_id = await game_engine.start_new_game(story_id=story_id)
            guild = message.guild
            category = await guild.create_category(f"Game {game_id}")
            channel = await guild.create_text_channel("initialization", category=category)
            
            await game_engine.register_interface(game_id, {
                "type": "discord",
                "guild_id": str(guild.id),
                "channel_id": str(channel.id),
                "category_id": str(category.id)
            })

            await message.channel.send(f"✅ **Game Started!**\nID: `{game_id}`\nLocation: {channel.mention}")
            return
        except Exception as e:
            logging.error(f"Error in !start: {e}")
            await message.channel.send(f"❌ Error: {str(e)}")
            return

    if message.content == '!debug':
        game_data = await game_engine.find_game_by_channel(message.channel.id)
        if not game_data:
            await message.channel.send("This is not a game channel.")
            return
        debug_info = await game_engine.get_debug_info(game_data['id'])
        await message.channel.send(f"```json\n{debug_info}\n```")
        return

    if message.content == '!kill':
        try:
            game_data = await game_engine.find_game_by_channel(message.channel.id)
            if not game_data: return
            
            interface = game_data.get('interface', {})
            cat_id = int(interface.get('category_id'))
            category = message.guild.get_channel(cat_id)
            if category:
                for c in category.channels: await c.delete()
                await category.delete()
            await game_engine.kill_game(game_data['id'])
            return
        except Exception as e:
            logging.error(f"Error in !kill: {e}")
            return
            
    # 3. GAMEPLAY (The Brain Transplant)
    game_data = await game_engine.find_game_by_channel(message.channel.id)
    if game_data and game_data.get('status') == 'active' and not message.content.startswith('!'):
        try:
            # Show typing indicator while thinking
            async with message.channel.typing():
                response_text = await game_engine.process_player_input(
                    channel_id=message.channel.id,
                    user_input=message.content
                )
            
            # Reply
            await message.channel.send(response_text)
        except Exception as e:
            logging.error(f"Gameplay Error: {e}")
