import pytest
from unittest.mock import MagicMock, patch
from cartridges.foster_protocol.logic import FosterProtocol
from cartridges.foster_protocol.models import Caisson

@pytest.mark.asyncio
async def test_context_caching_prefix_integrity():
    """
    CRITICAL COST TEST:
    Verifies that the System Prompt is constructed with the SHARED RULES first,
    and UNIQUE IDENTITY last. 
    
    If this fails, Context Caching will break, and API costs will spike 4x.
    """
    
    # 1. Setup specific mock strings to verify order
    SHARED_RULES = "THE_LAWS_OF_PHYSICS_AND_LORE" * 50 # Make it long enough to matter
    UNIQUE_ID_1 = "I_AM_UNIT_001"
    UNIQUE_ID_2 = "I_AM_UNIT_002"
    
    # 2. Patch the helpers to return our controlled strings
    # UPDATED: We patch the new prompt accessor instead of the old class method
    with patch("cartridges.foster_protocol.prompts.get_base_prompt", return_value=SHARED_RULES), \
         patch("cartridges.foster_protocol.prompts.get_drone_identity_block", side_effect=[UNIQUE_ID_1, UNIQUE_ID_2]), \
         patch("random.randint", side_effect=[0, 1, 2]): # Force specific IDs
         
        cartridge = FosterProtocol()
        
        # 3. Initialize Game with 2 Players (generating 2 Drones)
        players = [{"id": "p1", "name": "Alice"}, {"id": "p2", "name": "Bob"}]
        result = await cartridge.on_game_start({"players": players})
        game_data = Caisson(**result["metadata"])
        
        # 4. Extract Drones
        drones = list(game_data.drones.values())
        assert len(drones) == 2
        d1 = drones[0]
        d2 = drones[1]
        
        # --- ASSERTION 1: PREFIX MATCH ---
        # Both drones MUST start with the exact same shared block
        assert d1.system_prompt.startswith(SHARED_RULES)
        assert d2.system_prompt.startswith(SHARED_RULES)
        
        # --- ASSERTION 2: SUFFIX UNIQUENESS ---
        # The unique identity must be at the END
        assert d1.system_prompt.endswith(UNIQUE_ID_1)
        assert d2.system_prompt.endswith(UNIQUE_ID_2)
        
        # --- ASSERTION 3: NO LEAKAGE ---
        # The unique ID of drone 2 should NOT appear in drone 1
        assert UNIQUE_ID_2 not in d1.system_prompt
        
        print("\n✅ CACHE CHECK PASSED: System Prompts share common prefix.")