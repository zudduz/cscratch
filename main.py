import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from langchain_google_vertexai import ChatVertexAI
from fastapi.middleware.cors import CORSMiddleware

# 1. Initialize FastAPI
app = FastAPI()

# Add CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.zudduz.com", "https://zudduz.com", "http://www.zudduz.com", "http://zudduz.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Initialize Gemini (Vertex AI)
llm = ChatVertexAI(
    model="gemini-2.5-flash",
    temperature=0.7,
    max_retries=1
)

# Data model for the request
class UserInput(BaseModel):
    message: str

# 3. The UI Endpoint (Serves the Browser Interface)
@app.get("/", response_class=HTMLResponse)
async def get_ui():
    with open("index.html", "r") as f:
        return f.read()

# 4. The AI Endpoint (The "Round Trip")
@app.post("/chat")
async def chat(input_data: UserInput):
    print(f"Received: {input_data.message}") # Logs to Cloud Logging
    
    try:
        # Call Gemini
        response = llm.invoke(input_data.message)
        return {"reply": response.content}
    except Exception as e:
        print(f"Error: {e}")
        return {"reply": f"System Error: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    # Local development convenience
    uvicorn.run(app, host="0.0.0.0", port=8080)