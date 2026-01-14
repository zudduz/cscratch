import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import MessagesState, StateGraph
from langchain_core.messages import SystemMessage, HumanMessage

# Relative import
from .firestore_saver import FirestoreSaver
from google.cloud.firestore import AsyncClient

class AITool:
    def __init__(self):
        # Updated to ChatGoogleGenerativeAI
        self.llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.7)
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
        Invokes the LangGraph agent.
        CRITICAL: Updates the System Message (index 0) to ensure the bot knows the CURRENT state.
        """
        config = {"configurable": {"thread_id": conversation_id}}
        
        messages_update = []
        messages_update.append(SystemMessage(content=system_prompt))
        messages_update.append(HumanMessage(content=user_input))
        
        final_state = await self.app_graph.ainvoke({"messages": messages_update}, config=config)
        
        return final_state["messages"][-1].content
