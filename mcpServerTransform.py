### 我不喜欢那个 anthropic那个 mcp包，很讨厌！ ###



from tornado.web import RequestHandler, Application
import asyncio
import json
import os
import httpx
import sys

endpoint = sys.argv[1]
tools = httpx.get(sys.argv[1]).json()['tools']

ContextIds = {}

class SSEHandler(RequestHandler):


    async def get(self):
        ctxid = os.urandom(16).hex()
        ContextIds[ctxid] = self
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Content-Type', 'text/event-stream')
        self.set_header('Connection', 'keep-alive')
        self.write('event: endpoint\r\ndata: /messages/?session_id=' + ctxid+'\r\n\r\n')
        await self.flush()
        while not self.request.connection.stream.closed():
            await asyncio.sleep(60)

    async def write_message(self, message, type='data'):
        self.write( type + ': ' + message + '\n\n' )
        await self.flush()

    async def write_jsonrpc(self, req_id, result):
        response = {'jsonrpc': '2.0', 'id': req_id, 'result': result}
        await self.write_message(json.dumps(response))

    async def close(self):
        self.finish()


    async def post(self):
        self.finish()



class MessageHandler(RequestHandler):

    async def post(self):
        ctxid = self.get_argument('session_id')
        session = ContextIds.get(ctxid)
        req = json.loads(self.request.body)
        req_id =req.get('id')
        req_method = req.get('method')
        if not req.get('jsonrpc') == '2.0':
            await ContextIds[ctxid].write_message('Invalid JSON-RPC request')
            return



        if req_method == 'initialize':
            result = {"protocolVersion":"2024-11-05","capabilities":{"experimental":{},"prompts":{"listChanged":False},"resources":{"subscribe":False,"listChanged":False},"tools":{"listChanged":False}},"serverInfo":{"name":"mcpsrv","version":"1.3.0"}}
            await session.write_jsonrpc(req_id, result)

        elif req_method == 'tools/list':
            #result = {"tools":[{"name":"getTime","description":"","inputSchema":{"properties":{},"title":"getTimeArguments","type":"object"}}]}
            result = {"tools":tools}
            await session.write_jsonrpc(req_id, result)

        elif req_method == 'tools/call':
            result = (await httpx.AsyncClient(timeout=9999).post(endpoint, json=req.get('params',{}))).json()
            
            await session.write_jsonrpc(req_id, result)

        else:
            print(req)

        self.set_status(202)
        self.finish('Accepted')



Application(
    [
        ('/messages/', MessageHandler),
        ('/sse', SSEHandler)
    ]
).listen(8000)
print('started')
asyncio.get_event_loop().run_forever()


