from typing import Dict, Any

class FosterProtocol:
    def __init__(self):
        self.meta = {
            "name": "The Foster Protocol",
            "description": "A social deduction game aboard a dying starship.",
            "version": "0.1 (Stub)"
        }
        
        # STUB: In the future, we will load the .md files from the 'prompts/' folder.
        self.system_prompt = """
        ROLE: You are the Game Master for 'The Foster Protocol'.
        SETTING: A spaceship running on emergency power.
        TONE: Tense, mechanical, suspicious.
        OBJECTIVE: The players (Fosters) must survive the night.
        """

    async def play_turn(self, state: Dict[str, Any], user_input: str, tools) -> Dict[str, Any]:
        """
        The Core Loop for Foster Protocol.
        """
        
        # 1. State Check (Stub)
        # We pass the input to the AI with the system prompt.

        # 2. AI Generation
        # We use the Game ID as the conversation thread ID
        ai_response = await tools.ai.generate_response(
            system_prompt=self.system_prompt,
            conversation_id=state.get('id'), 
            user_input=user_input
        )
        
        return {
            "response": ai_response,
            "state_update": state 
        }
