import math


def humano(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}TB"


def velocidad_ema(prev_ts, prev_bytes, prev_ema, ts, bytes_bajados, tau=1.0):
    """Velocidad en bytes/seg suavizada con media movil exponencial.

    Si el tiempo transcurrido es casi nulo (updates simultaneos de una
    descarga segmentada), devuelve la EMA anterior sin tocarla para evitar
    picos por division entre un numero minusculo.
    """
    dt = ts - prev_ts
    if dt <= 0.05:
        return prev_ema
    inst = (bytes_bajados - prev_bytes) / dt
    if prev_ema is None:
        return inst
    alpha = 1 - math.exp(-dt / tau)
    return alpha * inst + (1 - alpha) * prev_ema


def bar(pct, width=10):
    pct = max(0, min(100, pct))
    llenos = round(pct / 100 * width)
    return "█" * llenos + "░" * (width - llenos)
