#!/usr/bin/env python3
"""SHARK41 demo-testing bot (screenshot mode). Needs Pillow. No market data API.
Send a chart screenshot -> bot reads the last 5 candle colors -> applies PATTERN (default G G R G R)
-> if it matches: signal UP/CALL for the next candle, else "no setup".
He taps WIN/LOSS under each signal; the bot logs it and keeps the real win rate.
Env: TELEGRAM_TOKEN (required). Optional: PATTERN, RUN_SECONDS, DB.
"""
import os, json, time, sqlite3, urllib.request, urllib.parse, tempfile
from datetime import datetime, timezone
from chart_reader import read_candles

TOKEN = os.environ["TELEGRAM_TOKEN"]
PATTERN = os.environ.get("PATTERN", "GGRGR")
DB = os.environ.get("DB", "shark41.db")
RUN_SECONDS = int(os.environ.get("RUN_SECONDS", "0"))   # 0 = run forever
LABEL = "DEMO ONLY - unverified until 50 logged trades"
NAMES = {"G": "green", "R": "red"}

db = sqlite3.connect(DB)
db.execute("""CREATE TABLE IF NOT EXISTS signals(id INTEGER PRIMARY KEY, created TEXT,
 reading TEXT, direction TEXT, outcome TEXT)""")
db.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")
db.commit()

def kv_get(k, d=None):
    r = db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return r[0] if r else d
def kv_set(k, v):
    db.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, str(v))); db.commit()

def tg(method, **p):
    data = urllib.parse.urlencode(p).encode()
    with urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data), timeout=60) as r:
        return json.loads(r.read())

def say(text, markup=None):
    chat = kv_get("chat")
    if not chat: return
    p = {"chat_id": chat, "text": text}
    if markup: p["reply_markup"] = json.dumps(markup)
    try: tg("sendMessage", **p)
    except Exception as e: print("send fail", e)

def stats():
    q = lambda o: db.execute("SELECT count(*) FROM signals WHERE outcome=?", (o,)).fetchone()[0]
    w, l = q("WIN"), q("LOSS")
    p = db.execute("SELECT count(*) FROM signals WHERE outcome IS NULL").fetchone()[0]
    n = w + l
    return w, l, p, n, (f"{100*w/n:.1f}%" if n else "n/a")

def download_photo(msg):
    fid = None
    if msg.get("photo"): fid = msg["photo"][-1]["file_id"]
    elif msg.get("document", {}).get("mime_type", "").startswith("image/"): fid = msg["document"]["file_id"]
    if not fid: return None
    path = tg("getFile", file_id=fid)["result"]["file_path"]
    out = tempfile.NamedTemporaryFile(suffix=".img", delete=False).name
    urllib.request.urlretrieve(f"https://api.telegram.org/file/bot{TOKEN}/{path}", out)
    return out

def handle_image(msg):
    if kv_get("on") != "1":
        say("Signals are OFF. Send /go first."); return
    f = download_photo(msg)
    try:
        colors, ok, note = read_candles(f, want=len(PATTERN))
    except Exception as e:
        colors, ok, note = [], False, "image error"
    finally:
        try: os.remove(f)
        except Exception: pass
    if not ok:
        say(f"Can't read this image reliably ({note}). Send a clear, uncropped screenshot of the chart with the last 5 candles visible. No signal.")
        return
    reading = "".join(colors)
    shown = " ".join(NAMES[c] for c in colors)
    if reading == PATTERN:
        cur = db.execute("INSERT INTO signals(created,reading,direction) VALUES(?,?,?)",
                         (datetime.now(timezone.utc).isoformat(), reading, "UP"))
        db.commit(); sid = cur.lastrowid
        say(f"I read: {shown}\n🦈 Setup matched. UP/CALL on the next candle.\n⚠️ {LABEL}\nWhen the candle closes, tap the result:",
            {"inline_keyboard": [[{"text": "✅ WIN", "callback_data": f"r:{sid}:W"},
                                  {"text": "❌ LOSS", "callback_data": f"r:{sid}:L"}]]})
    else:
        say(f"I read: {shown}\nNo setup. Wait.\n(Check I read it right. If not, send a clearer screenshot.)")

def handle_cb(cb):
    if str(cb["message"]["chat"]["id"]) != kv_get("chat"): return
    _, sid, res = cb["data"].split(":")
    row = db.execute("SELECT outcome FROM signals WHERE id=?", (sid,)).fetchone()
    tg("answerCallbackQuery", callback_query_id=cb["id"])
    if not row: return
    if row[0]: say(f"Signal #{sid} already logged as {row[0]}."); return
    db.execute("UPDATE signals SET outcome=? WHERE id=?", ("WIN" if res == "W" else "LOSS", sid)); db.commit()
    w, l, p, n, rate = stats()
    say(f"Logged #{sid}: {'WIN' if res=='W' else 'LOSS'}\nReal win rate: {rate} ({w}W/{l}L, {n}/50 logged)\n{LABEL}")

def handle(msg):
    cid = str(msg["chat"]["id"])
    t = (msg.get("text") or "").strip().lower().split("@")[0]
    if not kv_get("chat") and t in ("/start", "/help"): kv_set("chat", cid)   # first user locks the bot
    if cid != kv_get("chat"): return
    if t in ("/start", "/help"):
        say(f"SHARK41 ready. Send a chart screenshot and I'll check the last {len(PATTERN)} candles against your rule "
            f"({' '.join(NAMES[c] for c in PATTERN)} then UP).\n/go - signals on\n/stop - signals off\n/winrate - real win rate\n/last - last 10 signals\n\n{LABEL}")
    elif t == "/go": kv_set("on", 1); say("Signals ON. Send a screenshot. " + LABEL)
    elif t == "/stop": kv_set("on", 0); say("Signals OFF.")
    elif t == "/winrate":
        w, l, p, n, rate = stats()
        say(f"Real win rate: {rate}\n{w}W / {l}L, pending {p}\nLogged: {n}/50\n{LABEL}")
    elif t == "/last":
        rows = db.execute("SELECT id, created, COALESCE(outcome,'pending') FROM signals ORDER BY id DESC LIMIT 10").fetchall()
        say("\n".join(f"#{a} {b[:16]} UTC: {c}" for a, b, c in rows) or "No signals yet.")
    elif msg.get("photo") or msg.get("document"): handle_image(msg)

def main():
    off = int(kv_get("offset", 0)); t0 = time.time()
    print("SHARK41 running, pattern", PATTERN)
    while not (RUN_SECONDS and time.time() - t0 > RUN_SECONDS):
        try:
            for u in tg("getUpdates", offset=off, timeout=20).get("result", []):
                off = u["update_id"] + 1; kv_set("offset", off)
                try:
                    if "message" in u: handle(u["message"])
                    elif "callback_query" in u: handle_cb(u["callback_query"])
                except Exception as e: print("handler fail", e)
        except Exception as e:
            print("poll fail", e); time.sleep(5)

if __name__ == "__main__":
    main()
