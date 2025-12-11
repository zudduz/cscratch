import os
import uuid
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import AsyncGenerator, Tuple, Dict

# Vertex AI & LangChain Imports
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, BaseMessage

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
    model="gemini-2.5-flash",
    temperature=0.7,
    streaming=True # Streaming must be enabled for the new endpoint
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

# --- Helper Function for Chat Session Setup ---
def get_chat_session(input_data: UserInput) -> Tuple[str, Dict, BaseMessage]:
    """Creates a new chat session or loads an existing one."""
    thread_id = input_data.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    input_message = HumanMessage(content=input_data.message)
    return thread_id, config, input_message

# --- Endpoints ---

@app.post("/chat")
async def chat(input_data: UserInput):
    thread_id, config, input_message = get_chat_session(input_data)

    output = app_graph.invoke({"messages": [input_message]}, config=config)
    bot_reply = output["messages"][-1].content

    return {"reply": bot_reply, "thread_id": thread_id}

async def stream_generator(input_data: UserInput) -> AsyncGenerator[str, None]:
    """Yields server-sent events for the streaming chat response."""
    thread_id, config, input_message = get_chat_session(input_data)

    yield f"data: {json.dumps({'thread_id': thread_id})}\n\n"

    async for event in app_graph.astream_events(
        {"messages": [input_message]}, config=config, version="v2"
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
