from http.client import HTTPConnection, HTTPSConnection
import json
import threading
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class Client:
    def __init__(self, url, token):
        self.url, self.token = url.rstrip('/'), token
        parsed = urlsplit(self.url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('Expected an HTTP(S) robot address without a path or credentials')
        self.host, self.port = parsed.hostname, parsed.port
        self.connection_type = HTTPSConnection if parsed.scheme == 'https' else HTTPConnection
        self.connection = None
        self.request_lock = threading.Lock()

    def request(self, path, message=None):
        data = None if message is None else json.dumps(message, allow_nan=False).encode()
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}
        # Reuse one command connection; MJPEG retains its independent stream.
        # Serializing requests also protects the final stop during shutdown.
        # Never replay a failed motion command: the caller disarms on failure.
        with self.request_lock:
            try:
                if self.connection is None:
                    self.connection = self.connection_type(self.host, self.port, timeout=0.4)
                self.connection.request('GET' if message is None else 'POST', path, body=data, headers=headers)
                with self.connection.getresponse() as response:
                    payload = response.read()  # Consume fully before reusing the socket.
                    status, reason, will_close = response.status, response.reason, response.will_close
                if will_close:
                    self.connection.close()
                    self.connection = None
                if not 200 <= status < 300:
                    try:
                        reason = json.loads(payload).get('error', reason)
                    except (ValueError, AttributeError):
                        pass
                    raise RuntimeError(str(reason))
                return json.loads(payload)
            except Exception:
                if self.connection is not None:
                    self.connection.close()
                    self.connection = None
                raise

    def close(self):
        with self.request_lock:
            if self.connection is not None:
                self.connection.close()
                self.connection = None

    def video(self):
        req = Request(self.url + '/video.mjpg', headers={'Authorization': 'Bearer ' + self.token})
        return urlopen(req, timeout=3)


def jpeg_frames(stream):
    """Bounded MJPEG parser using Content-Length rather than JPEG markers."""
    while True:
        line = stream.readline(4096)
        if not line:
            return
        if not line.startswith(b'--FRAME'):
            continue
        length = None
        while True:
            line = stream.readline(4096)
            if not line:
                return
            if line in (b'\r\n', b'\n'):
                break
            if line.lower().startswith(b'content-length:'):
                length = int(line.split(b':', 1)[1])
        if length is None or not 1 <= length <= 4_000_000:
            raise ValueError('Invalid video frame size')
        data = bytearray()
        while len(data) < length:
            chunk = stream.read(length - len(data))
            if not chunk:
                return
            data.extend(chunk)
        yield bytes(data)
