def humano(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}TB"


def bar(pct, width=10):
    pct = max(0, min(100, pct))
    llenos = round(pct / 100 * width)
    return "█" * llenos + "░" * (width - llenos)
