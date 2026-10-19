from starlette.responses import JSONResponse
class BodyLimit:
    def __init__(self,app,max_bytes=65536):self.app=app;self.max_bytes=max_bytes
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope.get('method') not in {'POST','PUT','PATCH'}:
            return await self.app(scope,receive,send)
        chunks=[];size=0
        while True:
            message=await receive()
            if message['type']=='http.disconnect':return
            data=message.get('body',b'');size+=len(data)
            if size>self.max_bytes:
                return await JSONResponse({'detail':'Request body too large'},status_code=413)(scope,receive,send)
            chunks.append(data)
            if not message.get('more_body'):break
        sent=False
        async def replay():
            nonlocal sent
            if not sent:
                sent=True;return {'type':'http.request','body':b''.join(chunks),'more_body':False}
            return await receive()
        return await self.app(scope,replay,send)
