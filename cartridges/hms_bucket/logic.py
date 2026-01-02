from typing import Dict, Any

class HMSBucket:
    def __init__(self):
        self.meta = {
            "name": "HMS Bucket",
            "description": "A survival mystery on a sinking ship.",
            "version": "1.0"
        }
        
        # The System Prompt defines the "Board" and "Characters" for the AI
        self.system_prompt = """
        You are the Game Master for a game called 'HMS Bucket'.
        SETTING: A leaky frigate in the Royal Navy, circa 1790.
        TONE: Dark comedy, wet, miserable, slightly bureaucratic.
        OBJECTIVE: The ship is slowly sinking. The player must find the leak.
        
        RULES:
        1. If the user asks to "check the bucket", tell them it is full of holes.
        2. Keep responses brief (under 3 sentences).
        3. If the user fails to act, describe the water rising.
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
