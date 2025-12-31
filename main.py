import asyncio
import json
import logging
import os
import traceback
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List, Tuple

import discord
import nest_asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google.cloud import secretmanager
from google.cloud.exceptions import NotFound
from google.cloud.firestore import AsyncClient
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import MessagesState, StateGraph
from pydantic import BaseModel

# Custom Imports
from firestore_saver import FirestoreSaver

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
nest_asyncio.apply()  # Allow nested event loops for Discord + FastAPI

# --- Secret Manager Helper ---
def get_discord_token():
    """Retrieves the Discord API token from Google Secret Manager."""
    try:
        client = secretmanager.SecretManagerServiceClient()
        # Note: 'versions/latest' is used to get the most recent version
        name = "projects/171510694317/secrets/c-scratch-discord-api/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logging.error(f"Failed to retrieve Discord token: {e}")
        return None

# --- Discord Client Setup ---
intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)

@discord_client.event
async def on_ready():
    logging.info(f'Discord Bot Connected: We have logged in as {discord_client.user}')

@discord_client.event
async def on_message(message):
    if message.author == discord_client.user:
        return

    if message.content.startswith('!ping'):
        await message.channel.send('Pong! (Hello from Cloud Run)')

# --- FastAPI Lifespan (Startup/Shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Launch Discord Bot in background task
    token = get_discord_token()
    if token:
        asyncio.create_task(discord_client.start(token))
    else:
        logging.warning("Discord token not found. Bot will not start.")
    
    yield
    
    # Shutdown: Clean up Discord connection
    if not discord_client.is_closed():
        await discord_client.close()

# --- FastAPI Setup ---
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(www\.)?zudduz\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- LangGraph & AI Setup ---
llm = ChatVertexAI(
    model="gemini-2.5-flash",
    temperature=0.7,
    streaming=True
)

firestore_client = AsyncClient(database="sandbox")
checkpointer = FirestoreSaver(client=firestore_client, collection="conversations")

workflow = StateGraph(state_schema=MessagesState)

def call_model(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]}

workflow.add_node("model", call_model)
workflow.set_entry_point("model")

app_graph = workflow.compile(checkpointer=checkpointer)

class UserInput(BaseModel):
    message: str

# --- Helper Function for Chat Session Setup ---
async def get_chat_session(story_id: str, game_id: str, message: str) -> Tuple[RunnableConfig, List[BaseMessage]]:
    """Creates a new chat session or loads an existing one, adding instructions for new sessions."""
    thread_id = f"{story_id}-{game_id}"
    config = RunnableConfig(configurable={"thread_id": thread_id})

    try:
        existing_state = await app_graph.aget_state(config)
    except NotFound:
        existing_state = None

    messages_for_graph = []
    if existing_state is None or not existing_state.values.get('messages'):
        system_message_content = "You are a helpful and friendly AI assistant."
        scenario_path = f"scenarios/{story_id}.json"
        if os.path.exists(scenario_path):
            try:
                with open(scenario_path, "r") as f:
                    data = json.load(f)
                    # If the JSON is a scenario definition, dump it as context
                    system_message_content = json.dumps(data)
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        messages_for_graph.append(SystemMessage(content=system_message_content))

    messages_for_graph.append(HumanMessage(content=message))

    return config, messages_for_graph

# --- Endpoints ---

@app.get("/stories/")
def get_stories():
    """Returns a list of available stories."""
    logging.info("get_stories endpoint called")
    scenarios_dir = "scenarios"
    if not os.path.exists(scenarios_dir):
        return []
    
    stories = []
    for filename in os.listdir(scenarios_dir):
        if filename.endswith(".json"):
            story_id = filename[:-5] # Remove .json extension
            filepath = os.path.join(scenarios_dir, filename)
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                    stories.append({
                        "id": story_id,
                        "displayName": data.get("displayName"),
                        "placeholderText": data.get("placeholderText"),
                        "description": data.get("description")
                    })
            except (json.JSONDecodeError, FileNotFoundError) as e:
                logging.error(f"Error processing scenario file: {filename}, error: {e}")
                pass
    return stories

@app.get("/stories/{story_id}/games/{game_id}")
async def get_game_history(story_id: str, game_id: str):
    """Retrieves the conversation history for a given game."""
    thread_id = f"{story_id}-{game_id}"
    config = RunnableConfig(configurable={"thread_id": thread_id})
    try:
        state = await app_graph.aget_state(config)
    except NotFound:
        return []

    if not state or not state.values.get("messages"):
        return []

    messages = state.values["messages"]
    history = []
    for msg in messages:
        history.append({"type": msg.type, "content": msg.content})

    return history


@app.post("/stories/{story_id}/games/{game_id}/chat")
async def stream_chat(story_id: str, game_id: str, input_data: UserInput):
    """Endpoint for streaming chat responses using Server-Sent Events (SSE)."""

    async def stream_generator() -> AsyncGenerator[str, None]:
        """Yields server-sent events for the streaming chat response."""
        try:
            config, messages = await get_chat_session(story_id, game_id, input_data.message)

            yield f'data: {json.dumps({"game_id": game_id})}\n\n'

            async for event in app_graph.astream_events(
                {"messages": messages}, config=config, version="v2"
            ):
                kind = event["event"]
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if chunk.content:
                        yield f'data: {json.dumps({"token": chunk.content})}\n\n'
        except Exception as e:
            logging.error(f"Error in stream_generator: {e}\n{traceback.format_exc()}")
            yield f'data: {json.dumps({"error": str(e)})}\n\n'

    return StreamingResponse(stream_generator(), media_type="text/event-stream")

# Force redeploy