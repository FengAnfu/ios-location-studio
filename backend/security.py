"""Authentication and bounded requests for the local device controller."""
import os
import secrets
from urllib.parse import urlsplit

TOKEN = os.environ.get('FAKEGPS_TOKEN') or secrets.token_urlsafe(32)
MAX_BODY = 1_100_000


class LocalControlMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        headers = {k.lower(): v.decode('latin1') for k, v in scope['headers']}
        host = headers.get(b'host', '')
        origin = headers.get(b'origin')
        try:
            parsed_host = urlsplit('http://' + host)
            valid_host = (parsed_host.hostname in ('127.0.0.1', 'localhost', '::1')
                          and not parsed_host.username and not parsed_host.path
                          and not parsed_host.query and not parsed_host.fragment)
        except ValueError:
            valid_host = False
        valid_origin = origin is None or origin in ('http://' + host, 'https://' + host)

        async def reject(status):
            if scope['type'] == 'websocket':
                await send({'type': 'websocket.close', 'code': 1008})
            else:
                body = b'{"detail":"Request denied"}'
                await send({'type': 'http.response.start', 'status': status,
                            'headers': [(b'content-type', b'application/json')]})
                await send({'type': 'http.response.body', 'body': body})

        if not valid_host or not valid_origin:
            return await reject(403)
        if scope['type'] == 'websocket':
            protocols = scope.get('subprotocols', [])
            if len(protocols) != 2 or protocols[0] != 'fakegps' or not secrets.compare_digest(protocols[1].encode(), TOKEN.encode()):
                return await reject(401)
        elif scope['path'].startswith('/api/'):
            if not secrets.compare_digest(headers.get(b'authorization', '').encode(), ('Bearer ' + TOKEN).encode()):
                return await reject(401)
        if scope['type'] == 'http':
            chunks = []
            size = 0
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                chunk = message.get('body', b'')
                size += len(chunk)
                if size > MAX_BODY:
                    return await reject(413)
                chunks.append(chunk)
                if not message.get('more_body', False):
                    break
            consumed = False
            async def bounded_receive():
                nonlocal consumed
                if consumed:
                    return await receive()
                consumed = True
                return {'type': 'http.request', 'body': b''.join(chunks), 'more_body': False}
            async def secure_send(message):
                if message['type'] == 'http.response.start':
                    message['headers'] = list(message.get('headers', [])) + [
                        (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                        (b'x-frame-options', b'DENY'), (b'referrer-policy', b'no-referrer')]
                await send(message)
            return await self.app(scope, bounded_receive, secure_send)
        await self.app(scope, receive, send)
