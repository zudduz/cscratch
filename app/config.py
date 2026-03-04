import os
import google.auth
import uuid

# --- CONFIGURATION ---
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", str(uuid.uuid4()))
OPS_KEY = os.getenv("OPS_KEY", str(uuid.uuid4()))
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", os.environ.get("GCP_PROJECT_ID"))
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")

# --- CLOUD TASKS CONFIG ---
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")
TASK_QUEUE_NAME = os.environ.get("TASK_QUEUE_NAME", "")
WORKER_URL = os.environ.get("WORKER_URL", "") # Public facing URL for Cloud Tasks ingress

# Comma-separated list of Admin Discord IDs
ADMIN_USER_IDS = os.environ.get("ADMIN_USER_IDS", "").split(",")

# Fallback for Project ID if not injected
if not PROJECT_ID:
    try:
        _, PROJECT_ID = google.auth.default()
    except:
        PROJECT_ID = "sandbox-456821" # Fallback from your uploaded files