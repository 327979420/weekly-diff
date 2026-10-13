"""Download bounded image assets during builds; restore cached assets offline."""
from hashlib import sha256
from io import BytesIO
import logging
from pathlib import Path
import re
import shutil
import warnings
from urllib.parse import urlsplit

import requests

from weekly_diff.config import Config
from weekly_diff.dates import parse_issue_id
from weekly_diff.http import Http
from weekly_diff.models import Issue, Item


def local_image(item: Item, issue_id: str) -> str | None:
    """Accept only an issue-scoped WebP path, never arbitrary HTML/remote paths."""
    value = item.extra.get('image_local')
    if isinstance(value, str) and re.fullmatch(
            rf'assets/img/{re.escape(issue_id)}/[a-z0-9-]+\.webp', value):
        return value
    return None


def hero_item(issue: Issue) -> Item | None:
    keys = issue.sixty_seconds_keys[0] if issue.sixty_seconds_keys else issue.top[:1]
    return next((item for key in keys[:1] for item in issue.items() if item.key == key), None)


def _webp(data: bytes, cfg: Config) -> bytes:
    from PIL import Image, ImageOps

    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        try:
            original = Image.open(BytesIO(data))
        except Image.DecompressionBombError:
            raise ValueError('Image dimensions too large') from None
        with original:
            image = ImageOps.exif_transpose(original).convert('RGB')
            if image.width > cfg.images.max_width:
                image = image.resize((cfg.images.max_width, max(1, round(
                    image.height * cfg.images.max_width / image.width))), Image.Resampling.LANCZOS)
            while True:
                output = BytesIO()
                image.save(output, format='WEBP', quality=cfg.images.quality)
                if output.tell() <= cfg.images.target_bytes:
                    return output.getvalue()
                image.thumbnail((max(1, image.width * 3 // 4), max(1, image.height * 3 // 4)))
                if image.size == (1, 1):
                    raise ValueError('Image budget too small')


def _download(url: str, http: Http) -> bytes:
    parts = urlsplit(url)
    if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username:
        raise ValueError('Invalid image URL')
    with http.session.get(url, timeout=http.cfg.images.timeout_seconds, stream=True) as response:
        response.raise_for_status()
        if not response.headers.get('Content-Type', '').lower().startswith('image/'):
            raise ValueError('Not an image')
        limit = http.cfg.images.max_download_bytes
        if int(response.headers.get('Content-Length', 0)) > limit:
            raise ValueError('Image too large')
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError('Image too large')
        return bytes(data)


def cache_images(issue: Issue, cfg: Config, cache_dir: Path) -> None:
    parse_issue_id(issue.id)
    http = Http(cfg)
    try:
        for item in issue.items():
            item.extra.pop('image_local', None)
            if not item.image_url:
                continue
            try:
                data = _webp(_download(item.image_url, http), cfg)
                slug = sha256(item.key.encode()).hexdigest()[:24]
                target = cache_dir / issue.id / f'{slug}.webp'
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                item.extra['image_local'] = f'assets/img/{issue.id}/{slug}.webp'
            except (requests.RequestException, OSError, ValueError, ImportError, Warning):
                logging.getLogger(__name__).warning('Image unavailable; omitting thumbnail')
    finally:
        http.close()


def restore_images(issue: Issue, cache_dir: Path, out_dir: Path) -> list[Path]:
    written = []
    for item in issue.items():
        relative = local_image(item, issue.id)
        source = cache_dir / issue.id / Path(relative).name if relative else None
        if source and source.is_file():
            target = out_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            written.append(target)
        else:
            item.extra.pop('image_local', None)
    return written
