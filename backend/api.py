from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from fastapi.middleware.cors import CORSMiddleware
import asyncio, os, sys
from contextlib import AsyncExitStack
from typing import Optional
import logging, json
from groq import Groq


logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="MCP API", description="API for interacting with MCP server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PromptRequest(BaseModel):
    prompt: str
    model: str = "fast"  # Default to fast model

class MCPClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MCPClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.content = []
        self._initialized = True

    async def connect_to_server(self, command: str, args: list[str]):
        if self.session is not None:
            return

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=dict(os.environ)
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()
        response = await self.session.list_tools()
        logger.info("\nConnected to server with tools:")
        logger.info(json.dumps([tool.name for tool in response.tools]))

    async def process_prompt(self, input: str, model: str = "fast"):
        if self.session is None:
            raise RuntimeError("Session not initialized")

        # Example: Use Groq for LLM inference
        groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        prompt = f"""
You are an engineering talent dashboard assistant. The user prompt is: {input}
Use the available MCP tools to gather data and generate a summary.
"""

        # Optionally, call an MCP tool for data
        authors = await self.session.call_tool("list_authors")
        authors_str = "\n".join([f"{a['name']} (PRs: {a['pr_count']})" for a in authors])

        # Add MCP tool data to the prompt
        full_prompt = prompt + f"\n\nHere is the list of authors:\n{authors_str}\n\nGenerate an HTML dashboard summary."

        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": full_prompt,
                }
            ],
            model="llama-3-70b-8192",  # or another Groq-supported model
        )

        # Return the LLM's HTML output (strip code block markers if present)
        html = chat_completion.choices[0].message.content
        return html.replace("```html", "").replace("```", "")

    async def cleanup(self):
        if self.session is not None:
            await self.exit_stack.aclose()
            self.session = None

mcp_client = MCPClient()

@app.on_event("startup")
async def startup_event():
    cwd = os.getcwd()
    await mcp_client.connect_to_server(
        command=sys.executable,
        args=[os.path.join(cwd, "backend", "mcp_server.py")],
    )

@app.on_event("shutdown")
async def shutdown_event():
    await mcp_client.cleanup()

@app.post("/process")
async def process_prompt(request: PromptRequest):
    try:
        response = await mcp_client.process_prompt(request.prompt, request.model)
        mcp_client.content = []
        return response.replace("```html", "").replace("```", "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080) 