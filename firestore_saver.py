from __future__ import annotations

import pickle
from typing import Any, AsyncIterator, Optional, Dict

from google.cloud.firestore import AsyncClient
from pydantic import Field
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointTuple


class FirestoreSaver(BaseCheckpointSaver):
    client: AsyncClient = Field(
        default_factory=lambda: AsyncClient(database="sandbox"),
        description="The Firestore client to use for saving checkpoints.",
    )
    collection: str = Field(
        default="conversations",
        description="The name of the Firestore collection to use for storing checkpoints.",
    )

    def __init__(self, *, client: AsyncClient | None = None, collection: str = "conversations"):
        super().__init__()
        if client:
            self.client = client
        self.collection = collection

    @property
    def is_async(self) -> bool:
        return True

    def get(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        raise NotImplementedError("Use aget_tuple instead.")

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        doc_ref = self.client.collection(self.collection).document(thread_id)
        doc = await doc_ref.get()
        if doc.exists:
            checkpoint_bytes = doc.get("checkpoint")
            checkpoint = pickle.loads(checkpoint_bytes)
            return CheckpointTuple(
                config=config,
                checkpoint=checkpoint,
                parent_config=None,
            )
        return None

    def put(self, config: RunnableConfig, checkpoint: Checkpoint, metadata: Optional[Dict[str, Any]] = None) -> RunnableConfig:
        raise NotImplementedError("Use aput instead.")


    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        parent_config: Optional[RunnableConfig] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RunnableConfig:
        thread_id = config["configurable"]["thread_id"]
        doc_ref = self.client.collection(self.collection).document(thread_id)
        checkpoint_bytes = pickle.dumps(checkpoint)
        await doc_ref.set({"checkpoint": checkpoint_bytes})
        return config

    async def alist(self, filter: Optional[RunnableConfig] = None, *, before: Optional[RunnableConfig] = None, limit: Optional[int] = None) -> AsyncIterator[CheckpointTuple]:
        collection_ref = self.client.collection(self.collection)
        async for doc in collection_ref.stream():
            checkpoint_bytes = doc.get("checkpoint")
            checkpoint = pickle.loads(checkpoint_bytes)
            config = {"configurable": {"thread_id": doc.id}}
            yield CheckpointTuple(
                config=config,
                checkpoint=checkpoint,
                parent_config=None,
            )
