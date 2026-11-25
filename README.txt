SHARK41 screenshot-mode bot. Hosted on GitHub Actions (nothing runs on the phone).
Files: shark41_bot.py, chart_reader.py, .github/workflows/shark41.yml (shark41.db state is created/committed by the run).
Secret needed: TELEGRAM_TOKEN only. No market data API.
Use: /start once (locks bot to that chat), /go, send chart screenshot, tap WIN/LOSS under each signal. /stop /winrate /last.
Rule: PATTERN env, default GGRGR (G=green R=red, oldest first, rightmost = newest candle), then UP/CALL.
