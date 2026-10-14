"""Per-user desktop preferences; never stored in the repository."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def data_dir():
    return Path(os.environ.get('APPDATA', str(Path.home() / '.config'))) / 'VAMP'


def validate_url(url):
    url = url.strip().rstrip('/')
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('Enter an address like http://192.168.10.2:8765')
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError('Invalid port number') from exc
    return url


def load_settings():
    defaults = {'url': 'http://192.168.10.2:8765', 'token': 'vamp-prototype', 'weights': ''}
    try:
        saved = json.loads((data_dir() / 'operator.json').read_text())
        if not isinstance(saved, dict):
            return defaults
        candidate = {**defaults, **{k: v for k, v in saved.items() if k in defaults and isinstance(v, str)}}
        candidate['url'] = validate_url(candidate['url'])
        defaults = candidate
    except (OSError, ValueError):
        pass
    return defaults


def save_settings(url, token, weights=''):
    url = validate_url(url)
    if not token or not token.isascii():
        raise ValueError('Enter a non-empty ASCII token matching the Pi configuration')
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'operator.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'url': url, 'token': token, 'weights': weights}, indent=2))
    temporary.replace(path)

