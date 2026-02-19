from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel
import logging

from .. import persistence
from .. import config

# Dedicated router for external operations (Make.com, etc)
router = APIRouter(prefix="/ops", tags=["ops"], dependencies=[Depends(verify_ops_auth)])

async def verify_ops_auth(x_ops_key: str = Header(...)):
    """
    Strictly validates the request against the OPS_KEY.
    This key should be distinct from the INTERNAL_API_KEY.
    """
    if x_ops_key != config.OPS_KEY:
        logging.warning("Ops: Invalid key attempt.")
        raise HTTPException(status_code=403, detail="Invalid Ops Key")

class GiftPayload(BaseModel):
    user_id: str
    amount: int = "50"

@router.post("/gift")
async def ops_gift(payload: GiftPayload):
    """
    Endpoint for Make.com to gift tokens to a user.
    """
    logging.info(f"Ops: Gifting {payload.amount} to {payload.user_id}")
    
    try:
        # Use existing atomic transaction to create user (if new) and add balance
        new_balance = await persistence.db.adjust_user_balance(payload.user_id, payload.amount)
        
        return {
            "status": "success",
            "user_id": payload.user_id,
            "added": payload.amount,
            "new_balance": new_balance
        }
    except Exception as e:
        logging.error(f"Ops Gift Failed: {e}")
        raise HTTPException(status_code=500, detail="Transaction failed")