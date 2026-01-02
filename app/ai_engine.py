import logging
from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import MessagesState, StateGraph
from langchain_core.messages import SystemMessage, HumanMessage

# Relative import
from .firestore_saver import FirestoreSaver
from google.cloud.firestore import AsyncClient

class AITool:
    def __init__(self):
        self.llm = ChatVertexAI(model="gemini-2.5-flash", temperature=0.7)
        self.db = AsyncClient(database="sandbox")
        self.checkpointer = FirestoreSaver(client=self.db, collection="conversations")
        
        # Setup Graph
        workflow = StateGraph(state_schema=MessagesState)
        workflow.add_node("model", self._call_model)
        workflow.set_entry_point("model")
        self.app_graph = workflow.compile(checkpointer=self.checkpointer)

    def _call_model(self, state: MessagesState):
        return {"messages": [self.llm.invoke(state["messages"])]}

    async def generate_response(self, system_prompt: str, conversation_id: str, user_input: str) -> str:
        """
        Invokes the LangGraph agent with a specific System Prompt.
        """
        config = {"configurable": {"thread_id": conversation_id}}
        
        # Check if we need to initialize the thread with the system prompt
        # (Naive check: if thread is empty, add system message)
        state = await self.app_graph.aget_state(config)
        
        messages = []
        if not state.values:
            messages.append(SystemMessage(content=system_prompt))
        
        messages.append(HumanMessage(content=user_input))
        
        # Run the graph
        final_state = await self.app_graph.ainvoke({"messages": messages}, config=config)
        
        # Extract last message
        return final_state["messages"][-1].content
