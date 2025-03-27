from tornado.web import RequestHandler, Application
import asyncio
import json
import os
import logging

logger=logging.getLogger(__name__)

ContextIds = {}

class SSEServer(RequestHandler):

    def initialize(self):
        self._auto_finish = False

    def set_default_headers(self):
        self.set_header('Content-Type', 'text/event-stream')
        self.set_header('Cache-Control', 'no-cache')
        self.set_header('Connection', 'keep-alive')
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Headers', 'Content-Type')
        self.set_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')

    async def get(self):

        self.ctxid = os.urandom(16).hex()
        ContextIds[self.ctxid] = self
        await self.write_sse('/messages?session_id=' + self.ctxid, 'endpoint')


    async def write_sse(self, data, event='message'):
        self.write('event: ' + event + '\r\ndata: ' + data + '\r\n\r\n')
        await self.flush()

    async def write_jsonrpc(self, req_id, result):
        response = {'jsonrpc': '2.0', 'id': req_id, 'result': result}
        await self.write_sse( json.dumps(response) )

    def on_connection_close(self):
        ContextIds.pop(self.ctxid, None)


class RPCServer(RequestHandler):

    def set_default_headers(self):
        self.set_header('Content-Type', 'text/event-stream')
        self.set_header('Cache-Control', 'no-cache')
        self.set_header('Connection', 'keep-alive')
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Headers', 'Content-Type')
        self.set_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')


    async def post(self):
        ctxid = self.get_argument('session_id')
        session = ContextIds.get(ctxid)
        req = json.loads(self.request.body)
        logger.debug(req)
        req_method = req.get('method')
        func = self.for_name(req_method)
        if func:
            logger.debug(func)
            await func(req, session)
        self.set_status(202)
        self.finish('Accepted')

    def for_name(self, method):
        fn_name = 'with_' + method.replace('/', '_')
        fn = getattr(self, fn_name, None)
        return fn

    # 接下来只要实现这些就好了。。。。
    async def with_initilize(self, req, session):
        req_id = req.get('id')
        result = {"protocolVersion":"2024-11-05","capabilities":{"experimental":{},"prompts":{"listChanged":False},"resources":{"subscribe":False,"listChanged":False},"tools":{"listChanged":False}},"serverInfo":{"name":"mcpsrv","version":"1.3.0"}}
        await session.write_jsonrpc(req_id, result)

    async def with_tools_list(self, req, session):
        executor = self.settings.get('executor')
        try:
            executor and await executor.list_tools(req, session)
        except Exception as e:
            await session.write_jsonrpc(req['id'], {'tools': []})

    async def with_tools_call(self, req, session):
        executor = self.settings.get('executor')
        try:
            executor and await executor.call_tools(req, session)
        except Exception as e:
            await session.write_jsonrpc(req['id'], {'result': 'error'})


app = Application([
        ('/sse', SSEServer),
        ('/messages', RPCServer)
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
