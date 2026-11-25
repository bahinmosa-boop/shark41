"""Read candle colors from a chart screenshot. Needs Pillow.
Returns (colors, confidence_ok, note). colors = list of 'G'/'R', oldest first (rightmost = newest).
Defensive: if anything looks off, ok=False and the bot says it can't read the image."""
from PIL import Image
import statistics

def _classify(px):
    r, g, b = px[:3]
    if g - max(r, b) >= 40 and g >= 110: return "G"
    if r - max(g, b) >= 60 and r >= 140: return "R"
    return None

def read_candles(path, want=5):
    im = Image.open(path).convert("RGB")
    w0, h0 = im.size
    if w0 > 1400:                      # shrink big screenshots for speed
        im = im.resize((1400, int(h0 * 1400 / w0))); 
    w, h = im.size
    px = im.load()
    g = [0] * w; r = [0] * w
    for x in range(w):
        for y in range(int(h * 0.06), int(h * 0.94)):
            c = _classify(px[x, y])
            if c == "G": g[x] += 1
            elif c == "R": r[x] += 1
    # columns that are colored almost top to bottom are UI (buttons, bars), not candles
    colored = []
    for x in range(w):
        n = g[x] + r[x]
        colored.append(2 <= n <= 0.6 * h)
    runs, x = [], 0
    while x < w:
        if colored[x]:
            s = x
            while x < w and colored[x]: x += 1
            gs, rs = sum(g[s:x]), sum(r[s:x])
            runs.append((s, x - 1, "G" if gs > rs else "R", max(gs, rs) / max(1, gs + rs), sum(max(g[i], r[i]) for i in range(s, x))))
        else:
            x += 1
    if len(runs) < want:
        return [], False, "found only %d candle shapes" % len(runs)
    # drop tiny specks and oversized blobs (price tags, buttons)
    widths = [b - a + 1 for a, b, *_ in runs]
    med = statistics.median(widths)
    keep = [t for t in runs if 0.4 * med <= (t[1] - t[0] + 1) <= 2.2 * med and (t[1]-t[0]+1) >= 2]
    if len(keep) < want:
        return [], False, "candle shapes look irregular"
    last = keep[-want:]
    for t in last:
        if t[3] < 0.85:
            return [], False, "mixed colors in a candle"
    centers = [(a + b) / 2 for a, b, *_ in last]
    gaps = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
    mg = statistics.median(gaps)
    if mg < 2 or any(abs(gp - mg) > 0.4 * mg for gp in gaps):
        return [], False, "candle spacing is uneven (cropped, zoomed or covered?)"
    # rightmost candles must reach near the right half of the picture, else we likely read the wrong area
    if last[-1][1] < 0.4 * w:
        return [], False, "candles not found on the right side"
    return [t[2] for t in last], True, "ok"
