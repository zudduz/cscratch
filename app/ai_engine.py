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
        Invokes the LangGraph agent.
        CRITICAL: Updates the System Message (index 0) to ensure the bot knows the CURRENT state.
        """
        config = {"configurable": {"thread_id": conversation_id}}
        
        # 1. Fetch current history
        state = await self.app_graph.aget_state(config)
        messages_update = []
        
        # 2. Inject or Update System Prompt
        # If the history is empty, start with System Prompt.
        # If it exists, we want to OVERWRITE the first message if it's a SystemMessage, 
        # or prepending it effectively updates the "context" for the model in this turn.
        
        # A simple robust way: Just pass the SystemMessage in the input. 
        # LangGraph appends inputs. However, we want to refresh the "Persona".
        # Sending a SystemMessage *every turn* works well for simple agents.
        
        messages_update.append(SystemMessage(content=system_prompt))
        messages_update.append(HumanMessage(content=user_input))
        
        # 3. Run the graph
        # Note: By appending a new SystemMessage, we might bloat context. 
        # For a game prototype, this is fine and ensures the bot is always up to date.
        final_state = await self.app_graph.ainvoke({"messages": messages_update}, config=config)
        
        # 4. Extract last message
        return final_state["messages"][-1].content
