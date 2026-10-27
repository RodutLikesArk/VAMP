import copy
import threading
import time
import unittest
from unittest.mock import Mock

from pc.client import Client
from robot.camera import Camera
from robot.control import Controller
from robot.hardware import Hardware
from robot.main import Server, handler_for, control_loop
from test_controller import CONFIG


class ClientTests(unittest.TestCase):
    def test_heartbeats_reuse_one_connection_and_zero_command_keeps_armed(self):
        config = copy.deepcopy(CONFIG)
        hardware = Hardware(config, simulate=True)
        controller = Controller(hardware)
        camera = Camera(config['camera'], True)

        class CountingServer(Server):
            accepted = 0
            def get_request(self):
                result = super().get_request()
                self.accepted += 1
                return result

        server = CountingServer(('127.0.0.1', 0), handler_for(controller, camera, config['token']))
        quit_event = threading.Event()
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        control_thread = threading.Thread(target=control_loop, args=(controller, quit_event), daemon=True)
        server_thread.start()
        control_thread.start()
        client = Client(f'http://127.0.0.1:{server.server_port}', config['token'])
        try:
            client.request('/api/arm', {})
            for _ in range(12):
                status = client.request('/api/control', {'surge': .5})
                self.assertTrue(status['armed'])
                time.sleep(.1)
            client.request('/api/control', {})
            time.sleep(.05)
            status = client.request('/api/status')
            self.assertTrue(status['armed'])
            self.assertTrue(all(v == 0 for v in status['motors'].values()))
            self.assertEqual(server.accepted, 1)
            client.request('/api/stop', {})
        finally:
            client.close()
            quit_event.set()
            control_thread.join(1)
            server.shutdown()
            server.server_close()
            server_thread.join(1)

    def test_failed_motion_request_is_not_replayed_and_socket_is_discarded(self):
        client = Client('http://127.0.0.1:8765', 'test')
        connection = Mock()
        connection.getresponse.side_effect = TimeoutError('simulated timeout')
        client.connection_type = Mock(return_value=connection)
        with self.assertRaises(TimeoutError):
            client.request('/api/control', {'surge': 1})
        connection.request.assert_called_once()
        connection.close.assert_called_once()
        self.assertIsNone(client.connection)

    def test_server_rejection_keeps_reason_and_discards_connection(self):
        client = Client('http://127.0.0.1:8765', 'test')
        response = Mock(status=400, reason='Bad Request', will_close=False)
        response.read.return_value = b'{"error":"No valid IMU reading"}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        connection = Mock()
        connection.getresponse.return_value = response
        client.connection_type = Mock(return_value=connection)
        with self.assertRaisesRegex(RuntimeError, 'No valid IMU reading'):
            client.request('/api/control', {'stabilize': True})
        connection.request.assert_called_once()
        connection.close.assert_called_once()
        self.assertIsNone(client.connection)
