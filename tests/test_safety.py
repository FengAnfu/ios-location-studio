import os
os.environ['FAKEGPS_DEMO'] = '1'
import unittest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from backend.app import app, session
from backend.security import TOKEN
from backend import routing
from backend.devices import DeviceInfo
from backend.devices.ios import IOSLocationDriver, IOSDriverError


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, base_url='http://127.0.0.1:8765', raise_server_exceptions=False)
        self.client.__enter__()
        self.headers = {'Authorization': 'Bearer ' + TOKEN}

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def post(self, path, **kw):
        return self.client.post(path, headers=self.headers, **kw)

    def connect(self):
        self.assertEqual(self.post('/api/select', json={'udid': 'DEMO-IOS-0001'}).status_code, 200)

    def test_requires_auth(self):
        for path in ['/api/devices', '/api/status']:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.post('/api/clear').status_code, 401)

    def test_host_and_origin(self):
        for h in [{'Host': 'untrusted.example'}, {'Origin': 'https://untrusted.example'}]:
            self.assertEqual(self.client.get('/api/status', headers={**self.headers, **h}).status_code, 403)

    def test_only_ios_and_idempotent_selection(self):
        devices = self.client.get('/api/devices', headers=self.headers).json()['devices']
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]['platform'], 'ios')
        self.connect()
        first = session.driver
        self.connect()
        self.assertIs(first, session.driver)

    def test_teleport_and_restore(self):
        self.connect()
        self.assertEqual(self.post('/api/teleport', json={'lat': 31.2, 'lon': 121.5}).status_code, 200)
        self.assertEqual(session.driver.last, (31.2, 121.5))
        self.assertEqual(self.post('/api/clear').status_code, 200)
        self.assertIsNone(session.current)

    def test_failed_restore_keeps_state(self):
        self.connect()
        self.post('/api/teleport', json={'lat': 31.2, 'lon': 121.5})
        with patch.object(session.driver, 'clear', side_effect=RuntimeError('offline')):
            self.assertEqual(self.post('/api/clear').status_code, 502)
            self.assertIsNotNone(session.current)

    def test_bounds(self):
        for lat in [91, -91, 'nan', 'inf']:
            self.assertEqual(self.post('/api/teleport', json={'lat': lat, 'lon': 0}).status_code, 422)
        for speed in [0, -1, 31, 'nan']:
            self.assertEqual(self.post('/api/route', json={'points': [{'lat': 0, 'lon': 0}, {'lat': 0, 'lon': 1}], 'speed': speed}).status_code, 422)
        self.assertEqual(self.post('/api/route', json={'points': [{'lat': 0, 'lon': 0}, {'lat': 0, 'lon': 180}]}).status_code, 422)

    def test_gpx(self):
        self.assertEqual(self.post('/api/gpx', json={'gpx': '<gpx><trkpt lat="31" lon="121"/></gpx>'}).json()['points'], [[31,121]])
        for xml in ['<gpx', '<!DOCTYPE gpx><gpx/>', '<gpx><wpt lat="nan" lon="0"/></gpx>']:
            self.assertEqual(self.post('/api/gpx', json={'gpx': xml}).status_code, 400)
        self.assertEqual(self.post('/api/gpx', content=b'x'*1_100_001).status_code, 413)

    def test_websocket_rejects_untrusted(self):
        for options in [{}, {'subprotocols': ['fakegps', TOKEN], 'headers': {'origin': 'http://untrusted.example'}}]:
            with self.assertRaises(WebSocketDisconnect):
                with self.client.websocket_connect('ws://127.0.0.1:8765/ws', **options):
                    pass

    def test_authenticated_websocket(self):
        self.connect()
        with self.client.websocket_connect('ws://127.0.0.1:8765/ws', subprotocols=['fakegps', TOKEN], headers={'origin': 'http://127.0.0.1:8765'}) as ws:
            self.post('/api/teleport', json={'lat': 1, 'lon': 2})
            self.assertEqual(ws.receive_json(), {'type': 'position', 'lat': 1.0, 'lon': 2.0})


class DriverAndRouteTests(unittest.TestCase):
    def test_legacy_rejected_before_connecting(self):
        d = IOSLocationDriver(DeviceInfo('test', 'test', 'ios', '16.7'))
        with patch.object(d, '_start_loop') as start:
            with self.assertRaises(IOSDriverError):
                d.connect()
            start.assert_not_called()

    def test_clear_failure_propagates(self):
        d = IOSLocationDriver(DeviceInfo('test', 'test', 'ios', '17.0'))
        d._sim = Mock()
        with patch.object(d, '_call', side_effect=IOSDriverError('offline')):
            with self.assertRaises(IOSDriverError):
                d.clear()

    def test_long_route_is_lazy(self):
        points = [routing.Point(0, 0), routing.Point(0, 180)]
        with patch.object(routing, 'destination', wraps=routing.destination) as calc:
            iterator = routing.walk(points, 0.5, 0.5)
            self.assertEqual(next(iterator), points[0])
            calc.assert_not_called()
            next(iterator)
            self.assertEqual(calc.call_count, 1)


if __name__ == '__main__':
    unittest.main()
