from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from .. import persistence

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates") # We need to create this dir

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_index(request: Request):
    # Fetch active games first
    games = []
    # Note: You might need to add a proper query to persistence for "recent games"
    # For now, let's assume we scan active ones or top 20 recent
    ref = persistence.db.games_collection.order_by('created_at', direction='DESCENDING').limit(20)
    async for doc in ref.stream():
        games.append(doc.to_dict())
    
    return templates.TemplateResponse("index.html.j2", {"request": request, "games": games})

@router.get("/dashboard/{game_id}", response_class=HTMLResponse)
async def dashboard_game(request: Request, game_id: str):
    game = await persistence.db.get_game_by_id(game_id)
    logs = await persistence.db.get_game_logs(game_id)
    
    return templates.TemplateResponse("game_detail.html.j2", {
        "request": request, 
        "game": game.model_dump(), 
        "logs": logs
    })