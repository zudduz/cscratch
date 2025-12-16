from __future__ import annotations

import pickle
from typing import Any, AsyncIterator, Optional, Dict, Sequence

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
            doc_dict = doc.to_dict()
            checkpoint_bytes = doc_dict.get("checkpoint")
            metadata = doc_dict.get("metadata") or {}
            if "step" not in metadata:
                metadata["step"] = 0
            checkpoint = pickle.loads(checkpoint_bytes)
            return CheckpointTuple(
                config=config,
                checkpoint=checkpoint,
                parent_config=None,
                metadata=metadata,
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
        await self.aput_writes(config, [(config, checkpoint, metadata)], parent_config)
        return config

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple],
        parent_config: Optional[RunnableConfig] = None,
    ) -> None:
        batch = self.client.batch()
        for write in writes:
            if len(write) == 3:
                write_config, checkpoint, metadata = write
            else:
                write_config, checkpoint = write
                metadata = None

            thread_id = None
            if isinstance(write_config, str):
                thread_id = write_config
            elif isinstance(write_config, dict):
                configurable = write_config.get("configurable")
                if isinstance(configurable, str):
                    thread_id = configurable
                elif isinstance(configurable, dict):
                    thread_id = configurable.get("thread_id")

            if not thread_id:
                continue

            doc_ref = self.client.collection(self.collection).document(thread_id)
            checkpoint_bytes = pickle.dumps(checkpoint)
            if metadata and "__start__" in metadata:
                del metadata["__start__"]
            batch.set(doc_ref, {"checkpoint": checkpoint_bytes, "metadata": metadata or {}})
        await batch.commit()

    async def alist(self, filter: Optional[RunnableConfig] = None, *, before: Optional[RunnableConfig] = None, limit: Optional[int] = None) -> AsyncIterator[CheckpointTuple]:
        collection_ref = self.client.collection(self.collection)
        async for doc in collection_ref.stream():
            doc_dict = doc.to_dict()
            checkpoint_bytes = doc_dict.get("checkpoint")
            metadata = doc_dict.get("metadata") or {}
            if "step" not in metadata:
                metadata["step"] = 0
            checkpoint = pickle.loads(checkpoint_bytes)
            config = {"configurable": {"thread_id": doc.id}}
            yield CheckpointTuple(
                config=config,
                checkpoint=checkpoint,
                parent_config=None,
                metadata=metadata,
            )
