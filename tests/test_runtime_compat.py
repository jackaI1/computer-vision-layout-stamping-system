"""Catch incompatible HTTP middleware dependencies before browser uploads break."""
import asyncio

import pytest
from starlette.responses import Response
from streamlit.web.server.starlette.starlette_gzip_middleware import SelectiveGZipMiddleware


@pytest.mark.parametrize('encoding', [b'gzip', b'identity'])
def test_preview_media_responses_include_http_headers(encoding):
    # Streamlit overrides Starlette's gzip responder. An incompatible Starlette
    # release drops response.start for excluded types, breaking preview images.
    messages = []
    async def app(scope, receive, send):
        await Response(b'synthetic-image', media_type='image/png')(scope, receive, send)
    async def send(message):
        messages.append(message)
    async def receive():
        return {'type': 'http.request', 'body': b''}
    scope = {'type': 'http', 'method': 'GET', 'path': '/media/synthetic.png',
             'headers': [(b'accept-encoding', encoding)]}
    asyncio.run(SelectiveGZipMiddleware(app)(scope, receive, send))
    assert [m['type'] for m in messages] == ['http.response.start', 'http.response.body']
    assert messages[0]['status'] == 200
    assert messages[1]['body'] == b'synthetic-image'
