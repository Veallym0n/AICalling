import httpx
import asyncio
import urllib.parse
from httpx_sse import EventSource
import json
import logging

logger = logging.getLogger(__name__)

async def do_later(n, func, *args, **kwargs):
    await asyncio.sleep(n)
    return await func(*args, **kwargs)


class MCPClient:

    def __init__(self, mcp_server, openai_format=False, execute_timeout=60, max_alive=0):
        self.mcp_server = mcp_server
        self.mcp_server_tools = None
        self.openai_format = openai_format
        self.execute_timeout = int(execute_timeout) or 60
        self.session_addr = ''
        self.jsonrpc_id = 1
        self.jsonrpc_response = {}
        self.local_funcs = {}
        self.sse_client = None
        self.max_alive = max_alive


    @property
    def tools(self):
        return self.mcp_server_tools


    def add_local_tool(self, definition, func):
        self.mcp_server_tools.append(definition)
        func.isasync = asyncio.iscoroutinefunction(func)
        self.local_funcs[definition['function']['name']] = func

    async def close(self):
        self.sse_client and await self.sse_client.aclose()

    async def start_sse(self, on_init_callback=None):
        self.sse_client = httpx.AsyncClient(verify=False, timeout=httpx.Timeout(None, connect=10.0))
        try:
            async with self.sse_client.stream('GET', self.mcp_server) as response:
                event_source = EventSource(response)
                async for event in event_source.aiter_sse():
                    if self.sse_client.is_closed: break
                    logger.debug(f'Event: {event.event}, Data: {event.data}')
                    if event.event == 'endpoint':
                        self.session_addr = event.data if event.data.startswith('http') else urllib.parse.urljoin(self.mcp_server, event.data)
                        on_init_callback.set_result(True)
                    elif event.event == 'message':
                        try:
                            data = json.loads(event.data)
                            if data.get('id') and data.get('result'):
                                future = self.jsonrpc_response.get(data['id'])
                                if future: future.set_result(data)
                        except:
                            pass
        except httpx.ReadError:
            pass


    def _to_rpc(self, rpc_message):
        return httpx.AsyncClient().post(self.session_addr, json=rpc_message)


    async def handshake(self):

        if self.max_alive:
            asyncio.create_task(do_later(self.max_alive, self.close))

        fut = asyncio.Future()
        asyncio.create_task(self.start_sse(fut))
        await asyncio.wait_for(fut, timeout=60)
        await self._to_rpc({'method': 'initialize', 'params': {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': 'EzMCPCli', 'version': '0.1.1'}}, 'jsonrpc': '2.0', 'id': 0})
        await self._to_rpc({'method': 'notifications/initialized', 'jsonrpc': '2.0'})
        await self.get_tools()


    async def get_tools(self):
        fut = asyncio.Future()
        self.jsonrpc_response[1] = fut
        await self._to_rpc({'method': 'tools/list', 'jsonrpc': '2.0', 'id': 1})
        await asyncio.wait_for(fut, timeout=60)
        tools = fut.result().get('result', {}).get('tools', [])
        self.mcp_server_tools = tools if not self.openai_format else self._format_to_openai(tools)
        return self.mcp_server_tools


    def _format_to_openai(self, tools):
        toolset = []
        for tool in tools:
            toolset.append({
                'type':'function',
                'function': {
                    'name': tool.get('name', ''),
                    'description': tool.get('description', ''),
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            arg: { 'type': vdef.get('type', 'string'), 'description': vdef.get('description', '') or vdef.get('title', '') }
                            for arg, vdef in tool.get('inputSchema', {}).get('properties', {}).items()
                        },
                        'required': tool.get('inputSchema', {}).get('required', []),
                        'additionalProperties': False
                    },
                    'strict': True
                }
            })
        return toolset


    async def execute(self, name, args):
        logger.debug(f'Executing {name} with args: {args}')
        local_func = self.local_funcs.get(name)
        if local_func:
            return (await local_func(args)) if local_func.isasync else local_func(args)

        logger.debug(f'Executing MCP Tools {name} with args: {args}')
        self.jsonrpc_id += 1
        jsonrpc = { 'jsonrpc': '2.0', 'method': 'tools/call', 'params': { 'name': name, 'arguments': args }, 'id': self.jsonrpc_id }
        fut = asyncio.Future()
        self.jsonrpc_response[self.jsonrpc_id] = fut
        await self._to_rpc(jsonrpc)
        try:
            result = await asyncio.wait_for(fut, timeout=self.execute_timeout)
            return result.get('result',{})
        except asyncio.TimeoutError:
            return {"Error":"Timeout"}
        finally:
            self.jsonrpc_response.pop(self.jsonrpc_id, None)
