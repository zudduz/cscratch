from typing import Dict, Any

class HMSBucket:
    def __init__(self):
        self.meta = {
            "name": "HMS Bucket",
            "description": "A survival mystery on a sinking ship.",
            "version": "1.0"
        }
        
        self.system_prompt = """
        You are the Game Master for 'HMS Bucket'.
        """

    async def handle_input(self, state: Dict[str, Any], user_input: str, context: dict, tools) -> Dict[str, Any]:
        # --- RULE 1: Hardcoded Interactions ---
        if user_input.lower() == "look at bucket":
            return {
                "response": "It's a wooden bucket. It has a hole in the bottom.",
                "state_update": state 
            }

        # --- RULE 2: AI Narration ---
        ai_response = await tools.ai.generate_response(
            system_prompt=self.system_prompt,
            conversation_id=state.get('id'),
            user_input=user_input
        )
        
        return {
            "response": ai_response,
            "state_update": state 
        }
