import yt_dlp


def buscar_youtube(consulta, limite=12):
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True}) as ydl:
        datos = ydl.extract_info(f"ytsearch{limite}:{consulta}", download=False)
    return [
        {"title": e.get("title", "Sin titulo"), "url": e.get("url") or f"https://www.youtube.com/watch?v={e['id']}",
         "channel": e.get("channel") or e.get("uploader") or "", "duration": e.get("duration") or 0}
        for e in datos.get("entries", []) if e
    ]
