import json
import logging
import datetime
import asyncio
from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2

from . import config

class CloudTaskDispatcher:
    def __init__(self):
        self.client = None
        if config.WORKER_URL and config.TASK_QUEUE_NAME:
            try:
                self.client = tasks_v2.CloudTasksClient()
            except Exception as e:
                logging.warning(f"Failed to initialize CloudTasksClient: {e}")

    def enqueue_task(self, cartridge_id: str, game_id: str, operation: str, data: dict = None, delay_seconds: int = 0):
        if not self.client or not config.WORKER_URL or not config.TASK_QUEUE_NAME:
            logging.info(f"Local Dev Fallback: Executing task '{operation}' for {game_id} via asyncio")
            # Inline import to avoid circular dependency
            from . import game_engine
            
            async def _local_dispatch():
                if delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)
                payload_obj = {"operation": operation, "data": data or {}}
                try:
                    await game_engine.engine.dispatch_task(cartridge_id, game_id, payload_obj)
                except Exception as e:
                    logging.error(f"Local task execution failed: {e}")
            
            asyncio.create_task(_local_dispatch())
            return

        parent = self.client.queue_path(config.PROJECT_ID, config.GCP_REGION, config.TASK_QUEUE_NAME)
        url = f"{config.WORKER_URL.rstrip('/')}/ingress/cartridge/{cartridge_id}/game/{game_id}"
        
        payload = {
            "operation": operation,
            "data": data or {}
        }
        
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": url,
                "headers": {
                    "Content-Type": "application/json",
                    "x-internal-auth": config.INTERNAL_API_KEY
                },
                "body": json.dumps(payload).encode(),
            }
        }
        
        if delay_seconds > 0:
            timestamp = timestamp_pb2.Timestamp()
            timestamp.FromDatetime(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=delay_seconds))
            task["schedule_time"] = timestamp
            
        try:
            response = self.client.create_task(request={"parent": parent, "task": task})
            logging.info(f"Dispatched Cloud Task {response.name} for {game_id} ({operation})")
        except Exception as e:
            logging.error(f"Failed to dispatch Cloud Task for {game_id}: {e}")

dispatcher = CloudTaskDispatcher()