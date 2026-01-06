from typing import Dict, Any

class HMSBucket:
    def __init__(self):
        self.meta = {
            "name": "The Foster Protocol",
            "description": "Your crew is on a stranded ship. Your only hope for survival are orphaned maintenance bots.",
            "version": "1.0"
        }
        
        # The System Prompt defines the "Board" and "Characters" for the AI
        self.system_prompt = """
        You are the Game Master for a game called 'The Foster Protocol'.
        
        This game is a stub.
        """

    async def play_turn(self, state: Dict[str, Any], user_input: str, tools) -> Dict[str, Any]:
        """
        The Core Loop. The Engine calls this when the user types something.
       
        Args:
            state: The current state of the game (from Firestore).
            user_input: What the user typed in Discord.
            tools: A wrapper containing 'ai' and 'rng' capabilities.
        """
        
        # --- RULE 1: Hardcoded Interactions (The "Board Pieces") ---
        # Example: We can intercept commands before the AI sees them.
        if user_input.lower() == "look at bucket":
            return {
                "response": "It's a wooden bucket. It has a hole in the bottom. Truly useless.",
                "state_update": state # No change
            }

        # --- RULE 2: AI Narration ---
        # If no hard rules trigger, we ask the AI to narrate the result.
        
        # We inject the system prompt + conversation history
        ai_response = await tools.ai.generate_response(
            system_prompt=self.system_prompt,
            conversation_id=state.get('game_id'), # Use Game ID as thread ID
            user_input=user_input
        )
        
        return {
            "response": ai_response,
            "state_update": state 
        }
