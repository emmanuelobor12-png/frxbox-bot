import os
import time
import requests
import pandas as pd
import ta
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"]

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})

def get_price_data(pair):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{pair}=X?interval=5m&range=1d"
        r = requests.get(url, timeout=10)
        data = r.json()
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        return pd.Series(closes)
    except:
        return None

def analyze(pair):
    prices = get_price_data(pair)
    if prices is None or len(prices) < 50:
        return None

    rsi = ta.momentum.RSIIndicator(prices).rsi().iloc[-1]
    macd = ta.trend.MACD(prices)
    macd_line = macd.macd().iloc[-1]
    signal_line = macd.macd_signal().iloc[-1]
    bb = ta.volatility.BollingerBands(prices)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    current = prices.iloc[-1]

    score = 0
    reasons = []

    if rsi < 35:
        score += 1
        reasons.append(f"RSI oversold ({rsi:.1f})")
    elif rsi > 65:
        score -= 1
        reasons.append(f"RSI overbought ({rsi:.1f})")

    if macd_line > signal_line:
        score += 1
        reasons.append("MACD bullish")
    else:
        score -= 1
        reasons.append("MACD bearish")

    if current < bb_lower:
        score += 1
        reasons.append("Price below BB lower band")
    elif current > bb_upper:
        score -= 1
        reasons.append("Price above BB upper band")

    if score >= 2:
        direction = "⬆️ HIGHER"
        confidence = "High" if score == 3 else "Medium"
    elif score <= -2:
        direction = "⬇️ LOWER"
        confidence = "High" if score == -3 else "Medium"
    else:
        return None

    return {
        "pair": pair,
        "direction": direction,
        "confidence": confidence,
        "price": current,
        "reasons": reasons
    }

def send_signals():
    found = False
    for pair in PAIRS:
        result = analyze(pair)
        if result:
            found = True
            msg = (
                f"🤖 <b>FRX Signal Box</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"📊 Pair: <b>{result['pair']}</b>\n"
                f"🎯 Signal: <b>{result['direction']}</b>\n"
                f"💪 Confidence: <b>{result['confidence']}</b>\n"
                f"💰 Price: <b>{result['price']:.5f}</b>\n"
                f"📋 Reasons:\n"
                + "\n".join(f"  • {r}" for r in result['reasons']) +
                f"\n⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                f"━━━━━━━━━━━━━━\n"
                f"⚠️ Trade at your own risk"
            )
            send_message(msg)
            time.sleep(2)
    if not found:
        send_message("🔍 No strong signals right now. Checking again in 5 minutes...")

def handle_commands():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        r = requests.get(url, timeout=10)
        updates = r.json().get("result", [])
        if not updates:
            return
        last = updates[-1]
        update_id = last["update_id"]
        text = last.get("message", {}).get("text", "")
        chat_id = last.get("message", {}).get("chat", {}).get("id")

        requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={update_id+1}")

        if text.startswith("/analyze"):
            parts = text.split()
            pair = parts[1].upper() if len(parts) > 1 else "EURUSD"
            result = analyze(pair)
            if result:
                msg = (
                    f"🔎 <b>Analysis: {result['pair']}</b>\n"
                    f"Signal: <b>{result['direction']}</b>\n"
                    f"Confidence: <b>{result['confidence']}</b>\n"
                    f"Price: <b>{result['price']:.5f}</b>\n"
                    f"Reasons: {', '.join(result['reasons'])}"
                )
            else:
                msg = f"No clear signal for {pair} right now."
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}
            )
        elif text == "/start":
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": "👋 Welcome to FRX Signal Box!\n\nCommands:\n/analyze EURUSD - analyze a pair\n/start - this message\n\nAuto signals sent every 5 minutes!", "parse_mode": "HTML"}
            )
    except:
        pass

send_message("🚀 FRX Signal Box is now LIVE! Auto signals every 5 minutes.")

counter = 0
while True:
    handle_commands()
    if counter % 30 == 0:
        send_signals()
    counter += 1
    time.sleep(10)
