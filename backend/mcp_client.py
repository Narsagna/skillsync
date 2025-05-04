from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio, os, sys
from contextlib import AsyncExitStack

# Set required environment variables here if needed
env_vars = dict(os.environ)
# env_vars["LLAMA_API_KEY"] = "your_llama_api_key_here"  # Uncomment and set if needed

server_params = StdioServerParameters(
    command=sys.executable,  # This will use the current Python interpreter
    args=[os.path.join(os.path.dirname(__file__), "mcp_server.py")],
    env=env_vars,
)

async def main():
    stack = AsyncExitStack()
    read, write = await stack.enter_async_context(stdio_client(server_params))
    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    mcp_tools = await session.list_tools()

    print("Available MCP tools:")
    for tool in mcp_tools.tools:
        print(f"Tool name: {tool.name} - {tool.description}")

    # Example: Call a tool (e.g., list_authors)
    result = await session.call_tool("list_authors")
    print("Authors:", result)

    await stack.aclose()

if __name__ == "__main__":
    asyncio.run(main()) 