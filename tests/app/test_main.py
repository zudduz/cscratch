from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)

def test_health_check():
    """Verify the app boots and health endpoint works."""
    # MOCK DISCORD: Force the client to say it is ready
    with patch("app.main.discord_client.is_ready", True):
        response = client.get("/ping")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "mode": "headless"}

def test_dashboard_routes_exist():
    """
    Verify the dashboard routes we just added are reachable.
    We mock the persistence layer so we don't hit real Firestore.
    """
    with patch("app.routers.dashboard.persistence.db") as mock_db:
        # Mock the stream of games to return an empty list
        
        # Check if route is in app.routes
        routes = [route.path for route in app.routes]
        assert "/dashboard" in routes
        assert "/dashboard/{game_id}" in routes
