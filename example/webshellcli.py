
from chat.aichat import AIChat
from chat.mcpcli import MCPClient
import asyncio
import readline



async def test():
    mcp = MCPClient('http://mcp_server.com/sse')
    await mcp.handshake()

    ai = AIChat(model='openai')
    ai.mcp_tool = mcp

    while True:
        prompt = input('>>> ')
        if not prompt.strip():
            continue
        if prompt == 'exit':
            break
        async for content in ai.talk(prompt):
            print(content, end='')
        print()


asyncio.run(test())
