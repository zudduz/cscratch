from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel
import logging

from .. import persistence
from .. import config

async def verify_ops_auth(x_ops_key: str = Header(...)):
    """
    Strictly validates the request against the OPS_KEY.
    This key should be distinct from the INTERNAL_API_KEY.
    """
    if x_ops_key != config.OPS_KEY:
        logging.warning("Ops: Invalid key attempt.")
        raise HTTPException(status_code=403, detail="Invalid Ops Key")

# Dedicated router for external operations (Make.com, etc)
router = APIRouter(prefix="/ops", tags=["ops"], dependencies=[Depends(verify_ops_auth)])

class GiftPayload(BaseModel):
    user_id: str
    target_amount: int = 50

@router.post("/top-up")
async def top_up(payload: GiftPayload):
    """
    Endpoint for Make.com to gift tokens to a user.
    """
    logging.info(f"Ops: Topping up {payload.user_id} to at least {payload.target_amount}")
    
    try:
        # Use atomic transaction to set balance to max(current, target_amount)
        new_balance = await persistence.db.top_up_user_balance(payload.user_id, payload.target_amount)
        
        return {
            "status": "success",
            "user_id": payload.user_id,
            "target_amount": payload.target_amount,
            "new_balance": new_balance
        }
    except Exception as e:
        logging.error(f"Ops Gift Failed: {e}")
        raise HTTPException(status_code=500, detail="Transaction failed")
