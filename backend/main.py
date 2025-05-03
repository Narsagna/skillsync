import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI()

# Allow requests from your frontend (localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development only! In production, specify your domain.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LLAMA_API_URL = "https://api.llama.com/v1/chat/completions"
LLAMA_MODEL = "Llama-4-Maverick-17B-128E-Instruct-FP8"
LLAMA_API_KEY = os.getenv("LLAMA_API_KEY")

@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    prompt = data.get("prompt", "")

    if not LLAMA_API_KEY:
        return {"response": "Llama API key not set on server."}

    payload = {
        "model": LLAMA_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_completion_tokens": 1024,
        "temperature": 0.7
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLAMA_API_KEY}"
    }

    async with httpx.AsyncClient() as client:
        try:
            llama_response = await client.post(
                LLAMA_API_URL,
                json=payload,
                headers=headers,
                timeout=30
            )
            llama_response.raise_for_status()
            result = llama_response.json()
            # Extract the AI's reply from the response
            ai_message = result["completion_message"]["content"]["text"]
            return {"response": ai_message}
        except Exception as e:
            # Log the full response for debugging
            try:
                error_text = await llama_response.aread()
            except Exception:
                error_text = "No response body"
            return {"response": f"Error contacting Llama API: {str(e)}. Response: {error_text}"}