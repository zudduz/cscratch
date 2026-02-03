import os
import logging
from google.cloud import secretmanager
import google.auth
from dotenv import load_dotenv

# Load .env for local dev
load_dotenv()

# --- CONFIGURATION ---
SHARED_SECRET = os.getenv("SHARED_SECRET", "local-dev-secret")
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", os.environ.get("GCP_PROJECT_ID"))

# Fallback for Project ID if not injected
if not PROJECT_ID:
    try:
        _, PROJECT_ID = google.auth.default()
    except:
        PROJECT_ID = "sandbox-456821" # Fallback from your uploaded files

def get_discord_token():
    """
    Fetches the Discord Token.
    1. Checks Env Var (Local Dev)
    2. Checks Secret Manager (Prod)
    """
    if os.getenv("DISCORD_TOKEN"):
        return os.getenv("DISCORD_TOKEN")
        
    try:
        client = secretmanager.SecretManagerServiceClient()
        # Note: Using the resource name pattern from your original main.py
        name = f"projects/{PROJECT_ID}/secrets/c-scratch-discord-api/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logging.error(f"Failed to retrieve Discord token: {e}")
        return None