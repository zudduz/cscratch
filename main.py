
import os
import uuid
import json
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import AsyncGenerator, Tuple, Dict, List, Optional

# Vertex AI & LangChain Imports
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

# LangGraph Imports
from langgraph.graph import START, MessagesState, StateGraph
from google.cloud import firestore
from google.cloud.exceptions import NotFound
from langchain_google_firestore import FirestoreSaver

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI()

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
firestore_client = firestore.Client(database="sandbox")
checkpointer = FirestoreSaver(client=firestore_client, collection="conversations")

# --- The Graph Definition ---
workflow = StateGraph(state_schema=MessagesState)

def call_model(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]}

workflow.add_node("model", call_model)
workflow.add_edge(START, "model")

app_graph = workflow.compile(checkpointer=checkpointer)

class UserInput(BaseModel):
    message: str
    thread_id: str
    scenario: Optional[str] = None

# --- Helper Function for Chat Session Setup ---
def get_chat_session(input_data: UserInput) -> Tuple[RunnableConfig, List[BaseMessage]]:
    """Creates a new chat session or loads an existing one, adding instructions for new sessions."""
    logging.info(f"--- Getting chat session for thread_id: {input_data.thread_id} ---")
    config = RunnableConfig(configurable={"thread_id": input_data.thread_id})

    try:
        existing_state = app_graph.get_state(config)
    except NotFound:
        existing_state = None

    messages_for_graph = []
    if existing_state is None or not existing_state.values.get('messages'):
        logging.info("--- No state found, creating new conversation. ---")
        system_message_content = "You are a helpful and friendly AI assistant."
        if input_data.scenario:
            scenario_path = f"scenarios/{input_data.scenario}.json"
            if os.path.exists(scenario_path):
                try:
                    with open(scenario_path, "r") as f:
                        system_message_content = json.dumps(json.load(f))
                except (json.JSONDecodeError, FileNotFoundError):
                    pass
        messages_for_graph.append(SystemMessage(content=system_message_content))
    else:
        logging.info("--- State found, continuing conversation. ---")

    messages_for_graph.append(HumanMessage(content=input_data.message))
    logging.info(f"--- Messages for graph: {messages_for_graph} ---")

    return config, messages_for_graph

# --- Endpoints ---

@app.get("/scenarios")
def get_scenarios():
    """Returns a list of available scenarios."""
    scenarios_dir = "scenarios"
    if not os.path.exists(scenarios_dir):
        return []
    
    scenarios = []
    for filename in os.listdir(scenarios_dir):
        if filename.endswith(".json"):
            scenario_id = filename[:-5] # Remove .json extension
            filepath = os.path.join(scenarios_dir, filename)
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                    scenarios.append({
                        "id": scenario_id,
                        "displayName": data.get("displayName"),
                        "placeholderText": data.get("placeholderText")
                    })
            except (json.JSONDecodeError, FileNotFoundError) as e:
                logging.error(f"Error processing scenario file: {filename}, error: {e}")
                pass
    return scenarios

@app.get("/history/{thread_id}")
def get_history(thread_id: str):
    """Retrieves the conversation history for a given thread_id."""
    config = RunnableConfig(configurable={"thread_id": thread_id})
    try:
        state = app_graph.get_state(config)
    except NotFound:
        return []

    if not state or not state.values.get("messages"):
        return []

    messages = state.values["messages"]
    history = []
    for msg in messages:
        history.append({"type": msg.type, "content": msg.content})

    return history

@app.post("/chat")
async def chat(input_data: UserInput):
    config, messages = get_chat_session(input_data)
    output = app_graph.invoke({"messages": messages}, config=config)
    bot_reply = output["messages"][-1].content
    return {"reply": bot_reply, "thread_id": input_data.thread_id}

async def stream_generator(input_data: UserInput) -> AsyncGenerator[str, None]:
    """Yields server-sent events for the streaming chat response."""
    logging.info("--- Entered stream_generator ---")
    config, messages = get_chat_session(input_data)
    logging.info(f"--- Config: {config} ---")
    logging.info(f"--- Initial messages: {messages} ---")

    yield f'data: {json.dumps({"thread_id": input_data.thread_id})}\n\n'
    logging.info("--- Yielded thread_id ---")

    logging.info("--- Starting astream_events ---")
    async for event in app_graph.astream_events(
        {"messages": messages}, config=config, version="v2"
    ):
        logging.info(f"--- Received event: {event} ---")
        kind = event["event"]
        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                logging.info(f"--- Yielding chunk: {chunk.content} ---")
                yield f'data: {json.dumps({"token": chunk.content})}\n\n'
    logging.info("--- Finished astream_events ---")

@app.post("/stream-chat")
async def stream_chat(input_data: UserInput):
    """Endpoint for streaming chat responses using Server-Sent Events (SSE)."""
    return StreamingResponse(stream_generator(input_data), media_type="text/event-stream")
