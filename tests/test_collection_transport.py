import pytest
import asyncio
import json

from vibe_trending.collectors import terminal_frame
from vibe_trending import collectors
from vibe_trending.models import Plan, SeriesPlan


def test_unrelated_terminal_does_not_end_collection():
    assert not terminal_frame({'request_id': 'other', 'is_final': True, 'status': 'failed'}, 'ours')


def test_real_e2a_stream_end():
    assert terminal_frame({'request_id': 'ours', 'status': 'succeeded', 'is_final': True}, 'ours')
    assert not terminal_frame({'request_id': 'ours', 'status': 'in_progress', 'is_final': False}, 'ours')


def test_real_e2a_error_propagated_without_timeout():
    with pytest.raises(RuntimeError, match='model failed'):
        terminal_frame({'request_id': 'ours', 'status': 'failed', 'is_final': True,
                        'body': {'message': 'model failed'}}, 'ours')


@pytest.mark.asyncio
@pytest.mark.parametrize('failed', [True, False, 'timeout'])
async def test_kernel_cancelled_before_job_deleted(monkeypatch, failed):
    events, sockets = [], []
    trace = [{'tool': 'read_source', 'detail': {'error': 'unreadable'}}]

    class Response:
        def __init__(self, body):
            self.body = body
        def raise_for_status(self):
            pass
        def json(self):
            return self.body

    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, *args, **kwargs):
            return Response({'operation_id': 'operation'})
        async def get(self, *args):
            if failed == 'timeout':
                await asyncio.Event().wait()
            return Response({'result': None if failed else {'points': [1]},
                             'error': 'no evidence' if failed else '', 'trace': trace})
        async def delete(self, *args):
            events.append('delete')

    class Socket:
        async def __aenter__(self):
            sockets.append(self)
            self.index = len(sockets)
            return self
        async def __aexit__(self, *args):
            pass
        async def recv(self):
            return '{}'
        async def send(self, value):
            self.request = json.loads(value)
            events.append(self.request['req_method'])
        async def __aiter__(self):
            if self.index == 1:
                await asyncio.Event().wait()
            yield json.dumps({'request_id': self.request['request_id']})

    monkeypatch.setattr(collectors.httpx, 'AsyncClient', lambda **kwargs: Client())
    monkeypatch.setattr(collectors.websockets, 'connect', lambda *args, **kwargs: Socket())
    series = SeriesPlan(name='test', indicator='test')
    backend = collectors.JiuwenSwarmCollector()
    if failed == 'timeout':
        backend.timeout = 0.01
        with pytest.raises(collectors.CollectionFailure, match='超时'):
            await backend.collect(series, Plan(title='test', series=[series]))
    elif failed:
        with pytest.raises(collectors.CollectionFailure, match='no evidence') as error:
            await backend.collect(series, Plan(title='test', series=[series]))
        assert error.value.trace == trace
    else:
        assert await backend.collect(series, Plan(title='test', series=[series])) == {'points': [1]}
    assert events == ['chat.send', 'chat.interrupt', 'delete']
    assert sockets[0].request['session_id'] == sockets[1].request['session_id']
