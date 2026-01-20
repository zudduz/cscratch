import sys
import os
from unittest.mock import MagicMock

# --- 1. GLOBAL MOCKS (The "Air Gap") ---
# We force Python to use Fake objects for Google Cloud.
# This prevents the app from trying to connect to real servers during import.

# Create a generic mock
mock_cloud = MagicMock()

# Patch the specific modules your app imports
sys.modules["google.cloud"] = mock_cloud
sys.modules["google.cloud.firestore"] = mock_cloud
sys.modules["google.cloud.secretmanager"] = mock_cloud
sys.modules["google.cloud.logging"] = mock_cloud
sys.modules["langchain_google_vertexai"] = mock_cloud

# --- 2. ENVIRONMENT VARIABLES ---
# Set dummy values so os.environ.get() doesn't fail
os.environ["GCP_PROJECT_ID"] = "test-project"
os.environ["SERVICE_NAME"] = "test-service"

# --- 3. PYTEST HOOKS ---
import pytest

@pytest.fixture(autouse=True)
def mock_settings():
    """
    Automatically runs before every test.
    Ensures no real network calls slip through.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("GCP_PROJECT_ID", "test-project")
        yield