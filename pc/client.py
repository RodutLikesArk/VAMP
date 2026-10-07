import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class Client:
    def __init__(self, url, token):
        self.url, self.token = url.rstrip('/'), token

    def request(self, path, message=None):
        data = None if message is None else json.dumps(message, allow_nan=False).encode()
        req = Request(self.url + path, data=data, headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        try:
            with urlopen(req, timeout=0.4) as response:
                return json.load(response)
        except HTTPError as exc:
            try:
                reason = json.load(exc).get('error', str(exc))
            except Exception:
                reason = str(exc)
            raise RuntimeError(reason) from exc

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
