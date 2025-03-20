import sys
import tornado.web
import tornado.ioloop
import json
import optparse
import asyncio
from functools import reduce
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


# it will always be called ez.py, donnot modify the filename.
if __name__ == "__main__":
    sys.modules['ez'] = sys.modules['__main__']
    

class API:
    _shared_definitions = {}
    _shared_functions = {}
    _private_definitions = {}
    
    @classmethod
    def toolcall(cls, namespace='*', name=None, description='', kwargs={}):
        def wrapper(func):
            func_name = name or func.__name__
            buckets = []
            for ns in set([i.strip() for i in namespace.split(',') if i.strip()]):
                if ns == '*': 
                    buckets.append(API._shared_definitions)
                else:
                    if ns not in API._private_definitions:
                        API._private_definitions[ns] = {}
                    buckets.append(API._private_definitions[ns])

            defs = {
                'type': 'function',
                'function': {
                    'name': func_name,
                    'description': description,
                    'parameters': {
                        "type": "object",
                        "properties": {
                            k: {
                                'type': 'string',
                                'description': v.get('description', '')
                            }
                            for k, v in kwargs.items()
                        },
                        'required': [k for k, v in kwargs.items() if v.get('required', False)],
                        'additionalProperties': False
                    }
                },
                'strict': True
            }
            for bucket in buckets:
                bucket[func_name] = defs
            
            func.__toolcall__ = API._shared_definitions[func_name]
            API._shared_functions[func_name] = func
            print(f"function: {func_name} registed")
            return func
        return wrapper
    
    @classmethod
    def getAll(cls, *namepaces):
        if not namepaces:
            return list(API._shared_definitions.values())
        t =  [ns for ns in namepaces for ns in API._private_definitions.get(ns, {}).values()]
        if '*' in namepaces:
            return list(API._shared_definitions.values()) + t
        return list(reduce(lambda acc, x: acc if any(d['function']['name'] == x['function']['name'] for d in acc) else acc + [x], t, []))


class ModuleChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith('.py'):
            print(f"File is modified: {event.src_path}")
            self._reload_module(event.src_path)
    
    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith('.py'):
            print(f"Find New File: {event.src_path}")
            self._reload_module(event.src_path)
    
    def _reload_module(self, file_path):
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("module.name", file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            print(f"reload Module Successfully: {file_path}")
        except Exception as e:
            print(f"reload Module Failed: {e}")


class APIServer:

    optparser = optparse.OptionParser()
    optparser.add_option("-p", "--port", dest="port", default=8888, help="Tornado server port")
    optparser.add_option("-d", "--directory", dest="directory", default='./modules', help="Module directory")
    optparser.add_option("-e", "--endpoint", dest="endpoint", default='http://localhost:8888/jsonrpc', help="API endpoint")
    (options, args) = optparser.parse_args()

    def setup_watchdog(self, directory):
        handler = ModuleChangeHandler()
        observer = Observer()
        observer.schedule(handler, directory, recursive=True)
        observer.start()
        print(f"Monitoring: {directory}")
        return observer
    
    def start(self):
        # start directory monitor
        observer = self.setup_watchdog(APIServer.options.directory)

        class MixinCORS:
            def set_default_headers(self):
                self.set_header("Access-Control-Allow-Origin", "*")
                self.set_header("Access-Control-Allow-Headers", "*")
                self.set_header("Access-Control-Allow-Methods", "*")
                self.set_header("Access-Control-Allow-Credentials", "true")

            def write_error(self, status_code, **kwargs):
                self.set_header("Content-Type", "application/json")
                self.set_status(status_code)
                self.write(json.dumps({'error': self._reason}))
                self.finish()

            def options(self):
                self.set_status(204)
                self.finish()


        class ApiHandler(MixinCORS, tornado.web.RequestHandler):

            def get(self):
                namespaces = [i.strip() for i in self.get_argument('namespace', '').split(',') if i.strip()]
                self.set_header("Content-Type", "application/json")
                self.write(dict(
                    tools=API.getAll(*namespaces),
                    endpoint = APIServer.options.endpoint
                    ))
                
            async def post(self):
                self.set_header("Content-Type", "application/json")
                response = {"jsonrpc": "2.0"}
                try: 
                    data = json.loads(self.request.body)
                    response['id'] = data.get('id')
                    if data.get('method') and data.get('method') in API._shared_functions:
                        func = API._shared_functions[data.get('method')]
                        if asyncio.iscoroutinefunction(func):
                            result = await func(**data.get('params', {}))
                            response['result'] = result
                        else:
                            result = func(**data.get('params', {}))
                            response['result'] = result
                    else:
                        response['error'] = {'code': -32601, 'message': 'Method not found'}
                except Exception as e:
                    response['error'] = {'code': -32000, 'message': str(e)}
                self.write(json.dumps(response))
                self.finish()



        tornado.web.Application([
            (r"/jsonrpc", ApiHandler)
        ]).listen(APIServer.options.port)
        print(f"Tornado Server started at {APIServer.options.port} ...")
        try:
            tornado.ioloop.IOLoop.current().start()
        except KeyboardInterrupt:
            observer.stop()
        finally:
            observer.join()


def load_module(directory):
    import glob
    import importlib.util
    for File in glob.glob(directory+'/**/*.py', recursive=True):
        spec = importlib.util.spec_from_file_location("module.name", File)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)


if __name__ == "__main__":
    load_module(APIServer.options.directory)
    APIServer().start()