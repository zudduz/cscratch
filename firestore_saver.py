from __future__ import annotations

from typing import Any, Dict, List, Optional

from google.cloud import firestore
from langchain_core.runnables.utils import ConfigurableFieldSpec
from langchain_core.messages import BaseMessageHistory


class FirestoreSaver(BaseMessageHistory):

    def __init__(self, client: firestore.Client, collection: str):
        self.client = client
        self.collection = collection

    def get(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return None

        doc_ref = self.client.collection(self.collection).document(thread_id)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None

    def put(self, config: Dict[str, Any], values: Dict[str, Any]) -> None:
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return

        doc_ref = self.client.collection(self.collection).document(thread_id)
        doc_ref.set(values)

    @property
    def config_specs(self) -> List[ConfigurableFieldSpec]:
        return [
            ConfigurableFieldSpec(
                id="thread_id",
                name="Thread ID",
                description="The unique identifier for the conversation thread",
            ),
        ]
