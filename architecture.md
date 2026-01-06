# Chicken Scratch Architecture

## 1. High-Level Concept
**Chicken Scratch** is a "Game Console" running as a Discord Bot. It provides the hardware (I/O, Database, AI access), while **Cartridges** provide the software (Game Rules, Prompts, Logic).

* **The Console:** `app/` (Generic, doesn't know the rules).
* **The Cartridge:** `cartridges/` (Specific, contains the rules).

## 2. Component Layers

### A. The Interface (Discord Layer)
* **File:** `app/discord_client.py`
* **Role:** The "Controller."
* **Responsibility:**
    * Listens for raw text inputs.
    * Handles Commands (`!start`, `!nuke`).
    * Routing: Identifies if a message belongs to an active game channel and forwards it to the Engine.
    * **Rule:** Contains NO game logic.

### B. The Engine (Manager Layer)
* **File:** `app/game_engine.py`
* **Role:** The "Operating System."
* **Responsibility:**
    * **Session Management:** Creates unique Game IDs and persists them.
    * **Cartridge Loading:** Dynamically imports the correct Python module (e.g., `hms_bucket`) based on the game's `story_id`.
    * **Traffic Control:** Receives input, hands it to the cartridge, gets the result, and returns it to the Interface.

### C. The Intelligence (Tool Layer)
* **File:** `app/ai_engine.py`
* **Role:** The "GPU."
* **Responsibility:**
    * Wraps Google Vertex AI (Gemini).
    * Manages LangGraph memory (conversation history).
    * Exposed as a **Tool** to the cartridge. The cartridge decides *when* to call the AI.

### D. The Storage (Persistence Layer)
* **File:** `app/persistence.py`
* **Role:** The "Memory Card."
* **Technology:** Google Cloud Firestore.
* **Responsibility:**
    * Stores Game Metadata (Status, IDs).
    * Handles Idempotency (preventing double-processing of messages).
    * Saves Game State (Versioning included).

---

## 3. The Cartridge Contract
A Cartridge is an isolated folder (e.g., `cartridges/hms_bucket/`) containing a `logic.py`.

It **must** implement the following interface:

```python
class GameCartridge:
    def __init__(self):
        self.meta = { ... } # Name, Description, Version

    async def play_turn(self, state, user_input, tools):
        # 1. Inspect Input
        # 2. Apply Rules (Hardcoded logic)
        # 3. Use Tools (AI generation, RNG)
        # 4. Return { "response": str, "state_update": dict }
```
## 4. Data Flow (The "Turn")
1. User types "Look at the bucket" in #bucket-deck.
2. Discord Client sees the message, looks up the Channel ID in Firestore to find the game_id.
3. Game Engine loads the HMSBucket class.
4. Game Engine calls HMSBucket.play_turn().
5. Cartridge checks logic:
   - If "bucket": Return hardcoded response "It has a hole."
   - Else: Call tools.ai.generate_response() with the System Prompt.
6. Discord Client sends the final text back to the user.

## 5. Infrastructure
- **Compute:** Google Cloud Run (Containerized Python/FastAPI).
- **Database:** Firestore (NoSQL).
- **LLM:** Vertex AI (Gemini 1.5/2.5).