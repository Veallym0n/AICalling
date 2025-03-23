### 我特么要吐槽。你们搞那么多不同个格式干嘛啊？！！！干个坤啊？！！！ 美国都要跟俄罗斯瓜分乌克兰了，你们俩公司格式还能搞那么复杂？！###


import asyncio
import json
import urllib.parse
import httpx
from httpx_sse import EventSource
from traceback import print_exc



class MCPClient:

    def __init__(self, sse_url):
        self.sse_channel = sse_url
        urlo = urllib.parse.urlparse(sse_url)
        self.endpoint = urlo.scheme+'://'+urlo.netloc
        self.rpc_url = None
        self.rpc_id = 0
        self.tools = []
        self.tool_results = {}
        self.state = asyncio.Future()
    
    async def init(self):
        asyncio.create_task(self.connect())
        await asyncio.wait_for(self.state, timeout=10.0)

    def set_rpc_address(self, rpc_url):
        self.rpc_url = self.endpoint+rpc_url

    async def connect(self):
        """连接到MCP服务器并初始化"""
        client = httpx.AsyncClient(timeout=9999999)
        print("正在连接到MCP服务器...")
        async with client.stream(method='GET', url=self.sse_channel) as event_source:
            async for event in EventSource(event_source).aiter_sse():
                if event.event == 'endpoint':
                    self.set_rpc_address(event.data)
                    print(f"RPC端点: {self.rpc_url}")
                    await self.start_message()
                elif event.event == 'message':
                    try:
                        response = json.loads(event.data)
                        if response.get('result',{}).get('tools'):
                            self.tools = response['result']['tools']
                            print(f"获取到工具列表: {[t['name'] for t in self.tools]}")
                            self.state.set_result(True)
                        elif response.get('id') in self.tool_results:
                            self.tool_results[response.get('id')].set_result(response.get('result', {}))
                    except Exception as e:
                        print(f"消息处理错误: {e}")

    async def start_message(self):
        """初始化MCP会话"""
        await self.initialize()
        await self.notification_initialize()
        self.rpc_id += 1
        await self.list_tools()

    async def initialize(self):
        req = {'method': 'initialize', 'params': {'protocolVersion': '2024-11-05', 'capabilities': {'sampling': {}, 'roots': {'listChanged': True}}, 'clientInfo': {'name': 'mcp', 'version': '0.1.0'}}, 'jsonrpc': '2.0', 'id': self.rpc_id}
        await httpx.AsyncClient().post(self.rpc_url, json=req)

    async def notification_initialize(self):
        req = {'method': 'notifications/initialized', 'jsonrpc': '2.0'}
        await httpx.AsyncClient().post(self.rpc_url, json=req)

    async def list_tools(self):
        req = {'method': 'tools/list', 'jsonrpc': '2.0', 'id': self.rpc_id}
        await httpx.AsyncClient().post(self.rpc_url, json=req)

    async def call_tool(self, tool_name, params):
        """调用工具并等待响应"""
        self.rpc_id += 1
        req_id = self.rpc_id
        req = {'method': 'tools/call', 'params': {'name': tool_name, 'arguments': params}, 'jsonrpc': '2.0', 'id': req_id}
        
        print('Reqto:',req)



        # 创建Future以等待工具调用结果
        future = asyncio.Future()
        self.tool_results[req_id] = future
        # 发送请求
        await httpx.AsyncClient().post(self.rpc_url, json=req)
        
        try:
            # 等待结果
            result = await asyncio.wait_for(future, timeout=90.0)
            return result
        except asyncio.TimeoutError:
            del self.tool_results[req_id]
            raise Exception(f"工具调用超时: {tool_name}")
        




class ChatFactory:

    def use_OpenAI(self, *args, **kwargs):
        from openai import AsyncOpenAI
        return AsyncOpenAI(*args, api_key='hmmm', **kwargs)
    
        
    
class ChatService:

    def __init__(self, mcp_client, api_key=None, model="openai-large", useformat='azure'):
        self.mcp = mcp_client
        self.model = model
        self.format = useformat
        self.messages = []  # 对话历史
        self.aiservice = ChatFactory().use_OpenAI(
            base_url="https://text.pollinations.ai/openai"
        )

    


    async def chat_completion(self, query=None):
        """与大模型进行一轮对话"""
        if query:
            self.messages.append({"role": "user", "content": query})

        # 构建可用工具描述
        available_tools = [{
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description",''),
                "parameters": {
                    "type": "object",
                    "properties": {
                        k: {
                            "type": "string",
                            "description": v.get("description",'')
                        }
                        for k, v in tool.get("inputSchema", {}).get("properties", {}).items()
                    },
                    "required": list(tool.get("inputSchema", {}).get("required", []))
                }
            }
        } for tool in self.mcp.tools]

        try:
            # 调用大模型API
            response = await self.aiservice.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=available_tools,
                tool_choice="auto"
            )

            # 处理响应
            assistant_message = response.choices[0].message

            if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
                formatted_tool_calls = []
                for tc in assistant_message.tool_calls:
                    formatted_tool_calls.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })
            
                self.messages.append({"role": "assistant", "content": assistant_message.content, "tool_calls": formatted_tool_calls})

                # 处理每个工具调用
                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    
                    print(f"调用工具: {tool_name}, 参数: {tool_args}")
                    
                    # 执行工具调用
                    result = await self.mcp.call_tool(tool_name, tool_args)
                    
                    # 格式化工具返回结果
                    result_content = self._format_tool_result(result)
                    
                    # 将工具调用结果添加到消息历史

                    self.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_name,
                            "content": result_content
                        })
                # 再次调用AI获取最终响应
                return await self.chat_completion()
            
            # 返回助手的回复
            return assistant_message.content
            
        except Exception as e:
            error_msg = f"与AI对话出错: {str(e)}"
            print(error_msg)
            return error_msg

    def _format_tool_result(self, result):
        """格式化工具调用结果为字符串"""
        if isinstance(result, dict):
            if "content" in result and isinstance(result["content"], list):
                content = ""
                for item in result["content"]:
                    if item.get("type") == "text" and "text" in item:
                        content += item["text"]
                return content
        
        # 默认返回JSON字符串
        return json.dumps(result)





    # Example
    async def chat_loop(self):
        """交互式对话循环"""
        print("\n欢迎使用MCP对话助手！")
        print("输入问题开始对话，输入'退出'结束对话。")
        
        while True:
            try:
                user_input = input("\n问题: ")
                if user_input.lower() in ['退出', 'quit', 'exit']:
                    break
                    
                print("正在思考...")
                response = await self.chat_completion(user_input)
                print(f"\n答复: {response}")
                
            except Exception as e:
                print_exc()
                print(f"错误: {str(e)}")


async def main(sse_url, api_key=None):
    # 创建MCP客户端
    mcp_client = MCPClient(sse_url)
    await mcp_client.init()
    chat_service = ChatService(mcp_client, api_key)
    
    # 启动对话循环
    await chat_service.chat_loop()


if __name__ == "__main__":
    import sys
    
    # 获取命令行参数
    sse_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3999/sse"
    api_key = sys.argv[2] if len(sys.argv) > 2 else None
    
    asyncio.run(main(sse_url, api_key))



