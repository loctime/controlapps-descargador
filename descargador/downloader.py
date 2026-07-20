import os
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
CHUNK = 1 << 20  # 1 MB


def download(direct_url, destino, on_progress=None, should_pause=None, chunk_size=CHUNK):
    on_progress = on_progress or (lambda bajado, total: None)
    should_pause = should_pause or (lambda: False)

    ya = os.path.getsize(destino) if os.path.exists(destino) else 0
    headers = {"User-Agent": UA}
    if ya:
        headers["Range"] = f"bytes={ya}-"

    req = urllib.request.Request(direct_url, headers=headers)
    resp = urllib.request.urlopen(req, timeout=60)

    if resp.status == 206:
        total = int(resp.headers.get("Content-Range", "/0").split("/")[-1] or 0)
        modo = "ab"
    else:
        ya = 0
        modo = "wb"
        total = int(resp.headers.get("Content-Length", 0))

    if ya and total and ya >= total:
        return (True, ya, total, "completo")

    bajado = ya
    with open(destino, modo) as f:
        while True:
            if should_pause():
                return (False, bajado, total, "pausado")
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            try:
                f.write(chunk)
            except OSError as e:
                if getattr(e, "errno", None) == 28:  # No space left on device
                    return (False, bajado, total, "disco_lleno")
                raise
            bajado += len(chunk)
            on_progress(bajado, total)

    return (True, bajado, total, "completo")
