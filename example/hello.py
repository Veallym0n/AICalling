from ez import API
import asyncio

@API.toolcall(
    namespace='*,dns',
    name='whois',
    description='查询域名的注册信息(whois)',
    kwargs={
        'domain': { 'description': '域名', 'required': True }
    }
)
async def whois(domain):

    current_host = 'whois.iana.org'
    async def get_whois(domain):
        reader, writer = await asyncio.open_connection(current_host, 43)
        writer.write(f'{domain}\r\n'.encode())
        data = await reader.read()
        writer.close()
        return data.decode()
    
    for i in range(4):
        data = await get_whois(domain)
        refs = [d for d in data.split('\n') if d.startswith('whois:') or d.startswith('refer:')]
        if not refs:
            return data 
        current_host = refs[0].split(':', 1)[1].strip()

    return '没有找到...'

