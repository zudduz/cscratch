import logging
from google.cloud.firestore import AsyncClient
from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import MessagesState, StateGraph
from firestore_saver import FirestoreSaver

# --- AI & Database Setup ---
# Initialize the Gemini model
llm = ChatVertexAI(
    model="gemini-2.5-flash",
    temperature=0.7,
)

# Initialize Firestore for Conversation Memory
firestore_client = AsyncClient(database="sandbox")
checkpointer = FirestoreSaver(client=firestore_client, collection="conversations")

# --- LangGraph Workflow ---
workflow = StateGraph(state_schema=MessagesState)

def call_model(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]}

workflow.add_node("model", call_model)
workflow.set_entry_point("model")

# Export the compiled graph
app_graph = workflow.compile(checkpointer=checkpointer)