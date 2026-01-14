import logging
from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import MessagesState, StateGraph
from langchain_core.messages import SystemMessage, HumanMessage
from .firestore_saver import FirestoreSaver
from google.cloud.firestore import AsyncClient

class AITool:
    def __init__(self):
        self.db = AsyncClient(database="sandbox")
        self.checkpointer = FirestoreSaver(client=self.db, collection="conversations")
        self.client_cache = {} 
        
        # The graph structure is static, but the 'model' node will behave dynamically
        workflow = StateGraph(state_schema=MessagesState)
        workflow.add_node("model", self._call_model)
        workflow.set_entry_point("model")
        self.app_graph = workflow.compile(checkpointer=self.checkpointer)
        
        # Default active model
        self.current_model_name = "gemini-2.5-flash"

    def _get_client(self, model_name: str):
        if model_name not in self.client_cache:
            logging.info(f"AI Engine: Initializing Vertex client for {model_name}")
            # Use ChatVertexAI for Cloud Run IAM authentication (Keyless)
            self.client_cache[model_name] = ChatVertexAI(model=model_name, temperature=0.7)
        return self.client_cache[model_name]

    def _call_model(self, state: MessagesState):
        # Retrieve the specific model client for this request
        model = self._get_client(self.current_model_name)
        return {"messages": [model.invoke(state["messages"])]}

    async def generate_response(self, system_prompt: str, conversation_id: str, user_input: str, model_version: str = "gemini-2.5-flash") -> str:
        """
        Invokes the agent with a specific model version.
        """
        self.current_model_name = model_version
        config = {"configurable": {"thread_id": conversation_id}}
        
        messages_update = []
        messages_update.append(SystemMessage(content=system_prompt))
        messages_update.append(HumanMessage(content=user_input))
        
        final_state = await self.app_graph.ainvoke({"messages": messages_update}, config=config)
        return final_state["messages"][-1].content
