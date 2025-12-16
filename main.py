import os
import uuid
import json
import logging
import traceback
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.forwardedproxy import ForwardedProxyMiddleware
from typing import AsyncGenerator, Tuple, Dict, List, Optional

# Vertex AI & LangChain Imports
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

# LangGraph Imports
from langgraph.graph import MessagesState, StateGraph
from google.cloud.firestore import AsyncClient
from google.cloud.exceptions import NotFound

# Custom FirestoreSaver
from firestore_saver import FirestoreSaver

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI()

app.add_middleware(ForwardedProxyMiddleware)

# Add CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(www\.)?zudduz\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = ChatVertexAI(
    model="gemini-2.5-flash",
    temperature=0.7,
    streaming=True
)

# --- Persistence ---
firestore_client = AsyncClient(database="sandbox")
checkpointer = FirestoreSaver(client=firestore_client, collection="conversations")

# --- The Graph Definition ---
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
                    system_message_content = json.dumps(json.load(f))
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        messages_for_graph.append(SystemMessage(content=system_message_content))

    messages_for_graph.append(HumanMessage(content=message))

    return config, messages_for_graph

# --- Endpoints ---

@app.get("/stories/")
def get_stories():
    """Returns a list of available stories."""
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
                        "placeholderText": data.get("placeholderText")
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
