import os
import time
import requests
import pandas as pd
import ta
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CHF": "USDCHF=X",
    "USD/CAD": "USDCAD=X",
    "GBP/JPY": "GBPJPY=X",
    "EUR/JPY": "EURJPY=X",
    "EUR/GBP": "EURGBP=X",
    "AUD/JPY": "AUDJPY=X",
}

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})

def get_price_data(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range=2d"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        result = data["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        closes = [c for c in quote["close"] if c is not None]
        highs = [h for h in quote["high"] if h is not None]
        lows = [l for l in quote["low"] if l is not None]
        volumes = [v for v in quote["volume"] if v is not None]
        return {
            "closes": pd.Series(closes),
            "highs": pd.Series(highs),
            "lows": pd.Series(lows),
            "volumes": pd.Series(volumes)
        }
    except:
        return None

def get_sentiment(rsi, macd_line, signal_line, current, bb_upper, bb_lower):
    bullish = 0
    bearish = 0
    if rsi < 40: bullish += 1
    elif rsi > 60: bearish += 1
    if macd_line > signal_line: bullish += 1
    else: bearish += 1
    if current < bb_lower: bullish += 1
    elif current > bb_upper: bearish += 1
    if bullish > bearish: return "Bullish"
    elif bearish > bullish: return "Bearish"
    return "Neutral"

def get_volatility(closes):
    std = closes.pct_change().std()
    if std > 0.002: return "High"
    elif std > 0.001: return "Dynamic"
    return "Low"

def get_volume_status(volumes):
    if len(volumes) < 10: return "Normal"
    recent = volumes.iloc[-5:].mean()
    older = volumes.iloc[-20:-5].mean()
    if older == 0: return "Normal"
    ratio = recent / older
    if ratio > 1.5: return "Spiked"
    elif ratio < 0.7: return "Contracting"
    return "Normal"

def analyze(pair_name, symbol):
    data = get_price_data(symbol)
    if data is None or len(data["closes"]) < 50:
        return None

    closes = data["closes"]
    highs = data["highs"]
    lows = data["lows"]
    volumes = data["volumes"]

    rsi = ta.momentum.RSIIndicator(closes).rsi().iloc[-1]
    macd = ta.trend.MACD(closes)
    macd_line = macd.macd().iloc[-1]
    signal_line = macd.macd_signal().iloc[-1]
    bb = ta.volatility.BollingerBands(closes)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    current = closes.iloc[-1]

    # Support and Resistance
    support = round(lows.iloc[-20:].min(), 5)
    resistance = round(highs.iloc[-20:].max(), 5)

    # Scoring
    score = 0
    reasons = []
    ma_signals = []

    if rsi < 35:
        score += 2
        reasons.append(f"RSI Oversold ({rsi:.1f})")
        ma_signals.append("STRONG BUY")
    elif rsi < 45:
        score += 1
        reasons.append(f"RSI Low ({rsi:.1f})")
        ma_signals.append("BUY")
    elif rsi > 65:
        score -= 2
        reasons.append(f"RSI Overbought ({rsi:.1f})")
        ma_signals.append("STRONG SELL")
    elif rsi > 55:
        score -= 1
        reasons.append(f"RSI High ({rsi:.1f})")
        ma_signals.append("SELL")
    else:
        ma_signals.append("NEUTRAL")

    if macd_line > signal_line:
        score += 1
        reasons.append("MACD Bullish Crossover")
    else:
        score -= 1
        reasons.append("MACD Bearish Crossover")

    if current < bb_lower:
        score += 2
        reasons.append("Price Below BB Lower Band")
    elif current > bb_upper:
        score -= 2
        reasons.append("Price Above BB Upper Band")
    elif current < (bb_upper + bb_lower) / 2:
        score += 0.5
    else:
        score -= 0.5

    # Direction
    if score >= 2:
        direction = "⬆️ HIGHER"
        direction_short = "HIGHER"
        emoji = "🟢"
    elif score <= -2:
        direction = "⬇️ LOWER"
        direction_short = "LOWER"
        emoji = "🔴"
    else:
        return None

    # Risk Level
    abs_score = abs(score)
    if abs_score >= 4:
        risk = "LOW"
        risk_emoji = "🟢"
    elif abs_score >= 3:
        risk = "MEDIUM"
        risk_emoji = "🟡"
    else:
        risk = "HIGH"
        risk_emoji = "🔴"

    # MA Summary
    if score >= 3:
        ma_summary = "STRONG BUY"
        oscillator = "BUY"
    elif score >= 2:
        ma_summary = "BUY"
        oscillator = "NEUTRAL"
    elif score <= -3:
        ma_summary = "STRONG SELL"
        oscillator = "SELL"
    else:
        ma_summary = "SELL"
        oscillator = "NEUTRAL"

    sentiment = get_sentiment(rsi, macd_line, signal_line, current, bb_upper, bb_lower)
    volatility = get_volatility(closes)
    volume_status = get_volume_status(volumes)

    # RSI description
    if rsi < 35: rsi_desc = "Oversold - Reversal Likely"
    elif rsi > 65: rsi_desc = "Overbought - Pullback Likely"
    elif rsi > 55: rsi_desc = "Approaching Overbought"
    elif rsi < 45: rsi_desc = "Approaching Oversold"
    else: rsi_desc = "Neutral Range"

    # MACD description
    if macd_line > signal_line: macd_desc = "Bullish Momentum"
    else: macd_desc = "Bearish Momentum"

    # BB description
    if current < bb_lower: bb_desc = "Breaking Below Lower Band"
    elif current > bb_upper: bb_desc = "Breaking Above Upper Band"
    else: bb_desc = "Within Bands"

    return {
        "pair": pair_name,
        "direction": direction,
        "direction_short": direction_short,
        "emoji": emoji,
        "risk": risk,
        "risk_emoji": risk_emoji,
        "price": current,
        "support": support,
        "resistance": resistance,
        "sentiment": sentiment,
        "volatility": volatility,
        "volume": volume_status,
        "ma_summary": ma_summary,
        "oscillator": oscillator,
        "rsi": rsi,
        "rsi_desc": rsi_desc,
        "macd_desc": macd_desc,
        "bb_desc": bb_desc,
        "score": score,
        "time": datetime.now().strftime("%I:%M %p"),
        "date": datetime.now().strftime("%m/%d/%Y")
    }

def format_signal(r):
    return (
        f"{r['emoji']} <b>FRX SIGNAL BOX</b> {r['emoji']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>PAIR:</b> {r['pair']}\n"
        f"🎯 <b>SIGNAL: {r['direction']}</b>\n"
        f"⚠️ <b>RISK: {r['risk_emoji']} {r['risk']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 <b>MARKET OVERVIEW</b>\n"
        f"• Volatility: {r['volatility']}\n"
        f"• Sentiment: {r['sentiment']}\n"
        f"• Volume: {r['volume']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>MARKET SNAPSHOT</b>\n"
        f"• Current: {r['price']:.5f}\n"
        f"• Support (S1): {r['support']}\n"
        f"• Resistance (R1): {r['resistance']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📉 <b>TRADINGVIEW RATING</b>\n"
        f"• Summary: {r['ma_summary']}\n"
        f"• Moving Averages: {r['ma_summary']}\n"
        f"• Oscillators: {r['oscillator']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔬 <b>TECHNICAL ANALYSIS</b>\n"
        f"• RSI ({r['rsi']:.0f}): {r['rsi_desc']}\n"
        f"• MACD: {r['macd_desc']}\n"
        f"• Bollinger Bands: {r['bb_desc']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {r['time']} | T.TIME: 1 MINUTE\n"
        f"⚡ Signal valid for next 1-2 minutes\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Trade at your own risk</i>"
    )

def send_signals():
    found = False
    for pair_name, symbol in PAIRS.items():
        result = analyze(pair_name, symbol)
        if result:
            found = True
            send_message(format_signal(result))
            time.sleep(3)
    if not found:
        send_message("🔍 No strong signals across all pairs right now. Checking again in 5 minutes...")

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
            input_pair = parts[1].upper().replace("OTC", "").strip() if len(parts) > 1 else "EUR/USD"
            if "/" not in input_pair and len(input_pair) == 6:
                input_pair = input_pair[:3] + "/" + input_pair[3:]
            matched = None
            matched_symbol = None
            for pair_name, symbol in PAIRS.items():
                if input_pair in pair_name.replace("/", ""):
                    matched = pair_name
                    matched_symbol = symbol
                    break
            if not matched:
                matched = "EUR/USD"
                matched_symbol = "EURUSD=X"
            result = analyze(matched, matched_symbol)
            if result:
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": format_signal(result), "parse_mode": "HTML"}
                )
            else:
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": f"🔍 No clear signal for {matched} right now. Market is neutral.", "parse_mode": "HTML"}
                )

        elif text == "/pairs":
            pair_list = "\n".join([f"• {p}" for p in PAIRS.keys()])
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": f"📊 <b>Monitored Pairs:</b>\n{pair_list}\n\nUse /analyze EURUSD to check any pair instantly.", "parse_mode": "HTML"}
            )

        elif text == "/start":
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": "🚀 <b>FRX Signal Box Active!</b>\n\nCommands:\n/analyze EURUSD - instant analysis\n/analyze GBPUSD - analyze GBP/USD\n/pairs - see all monitored pairs\n\n⚡ Auto signals sent every 5 minutes!", "parse_mode": "HTML"}
            )
    except:
        pass

send_message("🚀 <b>FRX Signal Box UPGRADED!</b>\nNow monitoring 10 pairs with full market analysis.\nAuto signals every 5 minutes!")

counter = 0
while True:
    handle_commands()
    if counter % 30 == 0:
        send_signals()
    counter += 1
    time.sleep(10)
