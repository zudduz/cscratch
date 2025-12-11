import os
import uuid
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import AsyncGenerator, Tuple, Dict, List, Optional

# Vertex AI & LangChain Imports
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, BaseMessage, SystemMessage

# LangGraph Imports
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.checkpoint.memory import MemorySaver

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
    model="gemini-1.5-flash",
    temperature=0.7,
    streaming=True
)

# --- The Graph Definition ---
workflow = StateGraph(state_schema=MessagesState)

def call_model(state: MessagesState):
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

workflow.add_node("model", call_model)
workflow.add_edge(START, "model")

memory = MemorySaver()
app_graph = workflow.compile(checkpointer=memory)

class UserInput(BaseModel):
    message: str
    thread_id: str = None
    scenario: Optional[str] = None

# --- Helper Function for Chat Session Setup ---
def get_chat_session(input_data: UserInput) -> Tuple[str, Dict, List[BaseMessage]]:
    """Creates a new chat session or loads an existing one, adding instructions for new sessions."""
    thread_id = input_data.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Check if a checkpoint exists for this thread_id.
    checkpoint = memory.get(config)

    messages = []
    # If no checkpoint, it's a new conversation, so add the system message.
    if checkpoint is None:
        system_message_content = "You are a helpful and friendly AI assistant."
        if input_data.scenario:
            scenario_path = f"scenarios/{input_data.scenario}.json"
            if os.path.exists(scenario_path):
                try:
                    with open(scenario_path, "r") as f:
                        system_message_content = json.dumps(json.load(f))
                except (json.JSONDecodeError, FileNotFoundError):
                    pass # Keep the default message
        messages.append(SystemMessage(content=system_message_content))


    messages.append(HumanMessage(content=input_data.message))

    return thread_id, config, messages

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
            scenarios.append(filename[:-5]) # Remove .json extension
    return scenarios

@app.post("/chat")
async def chat(input_data: UserInput):
    thread_id, config, messages = get_chat_session(input_data)

    output = app_graph.invoke({"messages": messages}, config=config)
    bot_reply = output["messages"][-1].content

    return {"reply": bot_reply, "thread_id": thread_id}

async def stream_generator(input_data: UserInput) -> AsyncGenerator[str, None]:
    """Yields server-sent events for the streaming chat response."""
    thread_id, config, messages = get_chat_session(input_data)

    yield f"data: {json.dumps({'thread_id': thread_id})}\n\n"

    async for event in app_graph.astream_events(
        {"messages": messages}, config=config, version="v2"
    ):
        kind = event["event"]
        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield f"data: {json.dumps({'token': chunk.content})}\n\n"

@app.post("/stream-chat")
async def stream_chat(input_data: UserInput):
    """Endpoint for streaming chat responses using Server-Sent Events (SSE)."""
    return StreamingResponse(
        stream_generator(input_data),
        media_type="text/event-stream"
    )
