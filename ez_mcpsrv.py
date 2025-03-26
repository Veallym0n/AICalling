from tornado.web import RequestHandler, Application
import asyncio
import json
import os

ContextIds = {}

class MCPServer(RequestHandler):

    def set_default_headers(self):
        super().set_default_headers()
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Headers', 'Content-Type')
        self.set_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')

    async def get(self):
        if self.request.path != '/sse':
            self.set_status(404)
            self.finish('Not Found')
            return
        ctxid = os.urandom(16).hex()
        ContextIds[ctxid] = self
        self.set_header('Content-Type', 'text/event-stream')
        self.set_header('Connection', 'keep-alive')
        await self.write_sse('/messages/?session_id=' + ctxid, 'endpoint')
        while not self.request.connection.stream.closed():
            await asyncio.sleep(0)
    
    async def write_sse(self, data, event='message'):
        self.write('event: ' + event + '\r\ndata: ' + data + '\r\n\r\n')
        await self.flush()

    async def write_jsonrpc(self, req_id, result):
        response = {'jsonrpc': '2.0', 'id': req_id, 'result': result}
        self.write_sse( json.dumps(response) )
        await self.fliush()

    async def post(self):
        if not self.request.path.startswith('/messages/'):
            self.set_status(404)
            self.finish('Not Found')
            return
        ctxid = self.get_argument('session_id')
        session = ContextIds.get(ctxid)
        req = json.loads(self.request.body)
        req_id =req.get('id')
        req_method = req.get('method')
        if req_method == 'initialize':
            result = {"protocolVersion":"2024-11-05","capabilities":{"experimental":{},"prompts":{"listChanged":False},"resources":{"subscribe":False,"listChanged":False},"tools":{"listChanged":False}},"serverInfo":{"name":"mcpsrv","version":"1.3.0"}}
            await session.write_jsonrpc(req_id, result)

        elif req_method == 'tools/list':
            executor = self.settings.get('executor')
            executor and executor.list_tools(req, session)

        elif req_method == 'tools/call':
            executor = self.settings.get('executor')
            executor and executor.call_tools(req, session)

        self.set_status(202)
        self.finish('Accepted')



app = Application([
        ('/sse', MCPServer),
        ('/messages/', MCPServer)
    ])


def example():
    class Exector:
        async def list_tools(self, req, session):
             # 返回工具列表, 最好区分一下Anthropic和OpenAI的工具(默认用Anthropic的吧，OpenAI现在在mcp这块就是一个受...的存在)
            result = {"result": []}
            await session.write_jsonrpc(req['id'], result)

        async def call_tools(self, req, session):
            # 执行工具, 返回结果，比如再调用一次远程啥的.....
            result = {"result": 'ok'}
            await session.write_jsonrpc(req['id'], result)
    
    app.settings['executor'] = Exector()




if __name__ == '__main__':
    app.listen(15678)
    asyncio.get_event_loop().run_forever()
