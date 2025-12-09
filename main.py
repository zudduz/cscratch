import os
import uuid
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# Vertex AI & LangChain Imports
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# LangGraph Imports
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.checkpoint.memory import InMemorySaver

app = FastAPI()

# Add CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.zudduz.com", "https://zudduz.com", "http://www.zudduz.com", "http://zudduz.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.7
)

# --- 2. The Graph Definition ---
# We use the pre-built "MessagesState" which automatically handles 
# appending new messages to history.
workflow = StateGraph(state_schema=MessagesState)

# Define the node that calls Gemini
def call_model(state: MessagesState):
    response = llm.invoke(state["messages"])
    # We return a list, and LangGraph knows to APPEND it to the existing state
    return {"messages": [response]}

# Build the graph
workflow.add_edge(START, "model")
workflow.add_node("model", call_model)

# Compile with Memory (The crucial step)
memory = InMemorySaver()
app_graph = workflow.compile(checkpointer=memory)

class UserInput(BaseModel):
    message: str
    thread_id: str = None # Client will send this

@app.post("/chat")
async def chat(input_data: UserInput):
    # Use the provided thread_id or generate a new one
    thread_id = input_data.thread_id or str(uuid.uuid4())
    
    # Config tells LangGraph WHICH memory to load
    config = {"configurable": {"thread_id": thread_id}}
    
    # Prepare the input message
    input_message = HumanMessage(content=input_data.message)
    
    # Run the graph!
    # It automatically loads history for this thread_id, runs Gemini, and saves the new result.
    output = app_graph.invoke({"messages": [input_message]}, config=config)
    
    # Get the last message (Gemini's reply)
    bot_reply = output["messages"][-1].content
    
    return {
        "reply": bot_reply, 
        "thread_id": thread_id 
    }