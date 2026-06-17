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
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except:
        pass

def get_price_data(symbol, interval="5m", period="5d"):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        result = data["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        closes = pd.Series([c for c in quote["close"] if c is not None])
        highs = pd.Series([h for h in quote["high"] if h is not None])
        lows = pd.Series([l for l in quote["low"] if l is not None])
        opens = pd.Series([o for o in quote["open"] if o is not None])
        volumes = pd.Series([v for v in quote["volume"] if v is not None])
        return {"closes": closes, "highs": highs, "lows": lows, "opens": opens, "volumes": volumes}
    except:
        return None

def get_price_data_1h(symbol):
    return get_price_data(symbol, interval="1h", period="30d")

def detect_candlestick_pattern(opens, highs, lows, closes):
    if len(closes) < 3:
        return "No Pattern"
    o2, h2, l2, c2 = opens.iloc[-1], highs.iloc[-1], lows.iloc[-1], closes.iloc[-1]
    o1, h1, l1, c1 = opens.iloc[-2], highs.iloc[-2], lows.iloc[-2], closes.iloc[-2]
    body2 = abs(c2 - o2)
    body1 = abs(c1 - o1)
    lower_wick = min(o2, c2) - l2
    upper_wick = h2 - max(o2, c2)
    candle_range = h2 - l2 if h2 - l2 > 0 else 0.0001
    if c1 < o1 and c2 > o2 and c2 > o1 and o2 < c1:
        return "Bullish Engulfing"
    if c1 > o1 and c2 < o2 and c2 < o1 and o2 > c1:
        return "Bearish Engulfing"
    if lower_wick > 2 * body2 and upper_wick < body2 and body2 > 0:
        return "Hammer (Bullish)"
    if upper_wick > 2 * body2 and lower_wick < body2 and body2 > 0:
        return "Shooting Star (Bearish)"
    if body2 < 0.1 * candle_range:
        return "Doji (Indecision)"
    if len(closes) >= 3:
        o0, c0 = opens.iloc[-3], closes.iloc[-3]
        if c0 < o0 and body2 < 0.3 * abs(c0 - o0) and c2 > o2:
            return "Morning Star (Bullish)"
    return "No Pattern"

def analyze(pair_name, symbol):
    data = get_price_data(symbol)
    data_1h = get_price_data_1h(symbol)
    if data is None or len(data["closes"]) < 30:
        return None

    closes = data["closes"]
    highs = data["highs"]
    lows = data["lows"]
    opens = data["opens"]
    volumes = data["volumes"]
    current = closes.iloc[-1]

    # RSI
    rsi_val = ta.momentum.RSIIndicator(closes, window=14).rsi().iloc[-1]

    # MACD
    macd_ind = ta.trend.MACD(closes)
    macd_line = macd_ind.macd().iloc[-1]
    signal_line = macd_ind.macd_signal().iloc[-1]
    macd_hist = macd_ind.macd_diff().iloc[-1]

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(closes)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    bb_mid = bb.bollinger_mavg().iloc[-1]

    # EMA
    ema9 = ta.trend.EMAIndicator(closes, window=9).ema_indicator().iloc[-1]
    ema21 = ta.trend.EMAIndicator(closes, window=21).ema_indicator().iloc[-1]
    ema50 = ta.trend.EMAIndicator(closes, window=min(50, len(closes)-1)).ema_indicator().iloc[-1]

    # ADX
    try:
        adx_ind = ta.trend.ADXIndicator(highs, lows, closes, window=14)
        adx_val = adx_ind.adx().iloc[-1]
        adx_pos = adx_ind.adx_pos().iloc[-1]
        adx_neg = adx_ind.adx_neg().iloc[-1]
    except:
        adx_val, adx_pos, adx_neg = 20, 15, 15

    # Stochastic RSI
    try:
        stoch_rsi = ta.momentum.StochRSIIndicator(closes)
        stoch_k = stoch_rsi.stochrsi_k().iloc[-1]
        stoch_d = stoch_rsi.stochrsi_d().iloc[-1]
    except:
        stoch_k, stoch_d = 0.5, 0.5

    # ATR
    try:
        atr = ta.volatility.AverageTrueRange(highs, lows, closes, window=14).average_true_range().iloc[-1]
    except:
        atr = 0

    support = round(lows.iloc[-20:].min(), 5)
    resistance = round(highs.iloc[-20:].max(), 5)
    pattern = detect_candlestick_pattern(opens, highs, lows, closes)

    # Higher timeframe
    htf_trend = "Neutral"
    try:
        if data_1h and len(data_1h["closes"]) > 50:
            h_closes = data_1h["closes"]
            h_ema21 = ta.trend.EMAIndicator(h_closes, window=21).ema_indicator().iloc[-1]
            h_ema50 = ta.trend.EMAIndicator(h_closes, window=50).ema_indicator().iloc[-1]
            htf_trend = "Bullish" if h_ema21 > h_ema50 else "Bearish"
    except:
        pass

    # === SCORING (max 12 points) ===
    bull_points = 0
    bear_points = 0

    # RSI (3 points)
    if rsi_val < 35: bull_points += 3
    elif rsi_val < 45: bull_points += 2
    elif rsi_val < 50: bull_points += 1
    elif rsi_val > 65: bear_points += 3
    elif rsi_val > 55: bear_points += 2
    elif rsi_val > 50: bear_points += 1

    # MACD (2 points)
    if macd_line > signal_line: bull_points += 2
    else: bear_points += 2

    # Bollinger Bands (2 points)
    if current < bb_lower: bull_points += 2
    elif current < bb_mid: bull_points += 1
    elif current > bb_upper: bear_points += 2
    else: bear_points += 1

    # EMA (2 points)
    if current > ema9 and ema9 > ema21: bull_points += 2
    elif current > ema21: bull_points += 1
    elif current < ema9 and ema9 < ema21: bear_points += 2
    else: bear_points += 1

    # Stochastic RSI (2 points)
    if stoch_k < 0.3: bull_points += 2
    elif stoch_k < 0.5: bull_points += 1
    elif stoch_k > 0.7: bear_points += 2
    else: bear_points += 1

    # Pattern (1 point)
    if "Bullish" in pattern or "Hammer" in pattern or "Morning" in pattern:
        bull_points += 1
    elif "Bearish" in pattern or "Shooting" in pattern:
        bear_points += 1

    total_max = 12

    if bull_points > bear_points:
        confidence = min(99, round((bull_points / total_max) * 100))
        direction = "⬆️ HIGHER"
        direction_short = "HIGHER"
        emoji = "🟢"
        net = bull_points
    elif bear_points > bull_points:
        confidence = min(99, round((bear_points / total_max) * 100))
        direction = "⬇️ LOWER"
        direction_short = "LOWER"
        emoji = "🔴"
        net = bear_points
    else:
        return None

    # Lower threshold - fire if net >= 4 out of 12
    if net < 4:
        return None

    # Grade
    if confidence >= 70: grade = "A"
    elif confidence >= 55: grade = "B"
    else: grade = "C"

    # Risk
    if confidence >= 70: risk, risk_emoji = "LOW", "🟢"
    elif confidence >= 55: risk, risk_emoji = "MEDIUM", "🟡"
    else: risk, risk_emoji = "HIGH", "🔴"

    # MA Summary
    if confidence >= 65:
        ma_summary = "STRONG BUY" if direction_short == "HIGHER" else "STRONG SELL"
        oscillator = "BUY" if direction_short == "HIGHER" else "SELL"
    else:
        ma_summary = "BUY" if direction_short == "HIGHER" else "SELL"
        oscillator = "NEUTRAL"

    # Volatility
    std = closes.pct_change().std()
    volatility = "High" if std > 0.002 else ("Dynamic" if std > 0.001 else "Low")

    # Volume
    volume_status = "Normal"
    if len(volumes) > 20:
        rv = volumes.iloc[-5:].mean()
        ov = volumes.iloc[-20:-5].mean()
        if ov > 0:
            ratio = rv / ov
            volume_status = "Spiked" if ratio > 1.5 else ("Contracting" if ratio < 0.7 else "Normal")

    # Sentiment
    diff = bull_points - bear_points
    if direction_short == "HIGHER":
        sentiment = "Strongly Bullish" if diff >= 4 else "Bullish"
    else:
        sentiment = "Strongly Bearish" if diff <= -4 else "Bearish"

    # Descriptions
    if rsi_val < 30: rsi_desc = "Oversold - Strong Reversal"
    elif rsi_val < 40: rsi_desc = "Oversold Zone"
    elif rsi_val < 45: rsi_desc = "Approaching Oversold"
    elif rsi_val > 70: rsi_desc = "Overbought - Pullback Likely"
    elif rsi_val > 60: rsi_desc = "Approaching Overbought"
    else: rsi_desc = "Neutral Range"

    macd_desc = "Bullish Momentum" if macd_line > signal_line else "Bearish Momentum"

    if current < bb_lower: bb_desc = "Below Lower Band"
    elif current > bb_upper: bb_desc = "Above Upper Band"
    else: bb_desc = "Within Bands"

    if current > ema9 > ema21: ema_desc = "Bull Aligned (Price>EMA9>EMA21)"
    elif current < ema9 < ema21: ema_desc = "Bear Aligned (Price<EMA9<EMA21)"
    elif current > ema21: ema_desc = f"Above EMA21 ({ema21:.5f})"
    else: ema_desc = f"Below EMA21 ({ema21:.5f})"

    if stoch_k < 0.2: stoch_desc = f"Oversold ({stoch_k:.2f})"
    elif stoch_k > 0.8: stoch_desc = f"Overbought ({stoch_k:.2f})"
    else: stoch_desc = f"Neutral ({stoch_k:.2f})"

    if adx_val > 40: adx_desc = f"Very Strong Trend ({adx_val:.1f})"
    elif adx_val > 25: adx_desc = f"Strong Trend ({adx_val:.1f})"
    else: adx_desc = f"Weak/Ranging ({adx_val:.1f})"

    return {
        "pair": pair_name, "direction": direction,
        "direction_short": direction_short, "emoji": emoji,
        "grade": grade, "confidence": confidence,
        "risk": risk, "risk_emoji": risk_emoji,
        "price": current, "support": support, "resistance": resistance,
        "atr": atr, "sentiment": sentiment, "volatility": volatility,
        "volume": volume_status, "htf_trend": htf_trend,
        "ma_summary": ma_summary, "oscillator": oscillator,
        "rsi_val": rsi_val, "rsi_desc": rsi_desc,
        "macd_desc": macd_desc, "bb_desc": bb_desc,
        "ema_desc": ema_desc, "stoch_desc": stoch_desc,
        "adx_desc": adx_desc, "pattern": pattern,
        "time": datetime.now().strftime("%I:%M %p"),
    }

def format_signal(r):
    return (
        f"{r['emoji']} <b>FRX SIGNAL BOX</b> {r['emoji']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>PAIR:</b> {r['pair']}\n"
        f"🎯 <b>SIGNAL: {r['direction']}</b>\n"
        f"⭐ <b>GRADE: {r['grade']}</b> | 💪 <b>{r['confidence']}% Confidence</b>\n"
        f"⚠️ <b>RISK: {r['risk_emoji']} {r['risk']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 <b>MARKET OVERVIEW</b>\n"
        f"• Volatility: {r['volatility']}\n"
        f"• Sentiment: {r['sentiment']}\n"
        f"• Volume: {r['volume']}\n"
        f"• HTF Trend: {r['htf_trend']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>MARKET SNAPSHOT</b>\n"
        f"• Current: {r['price']:.5f}\n"
        f"• Support (S1): {r['support']}\n"
        f"• Resistance (R1): {r['resistance']}\n"
        f"• ATR: {r['atr']:.5f}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📉 <b>TRADINGVIEW RATING</b>\n"
        f"• Summary: {r['ma_summary']}\n"
        f"• Moving Averages: {r['ma_summary']}\n"
        f"• Oscillators: {r['oscillator']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔬 <b>TECHNICAL ANALYSIS</b>\n"
        f"• RSI ({r['rsi_val']:.0f}): {r['rsi_desc']}\n"
        f"• MACD: {r['macd_desc']}\n"
        f"• Bollinger Bands: {r['bb_desc']}\n"
        f"• EMA Trend: {r['ema_desc']}\n"
        f"• Stoch RSI: {r['stoch_desc']}\n"
        f"• ADX: {r['adx_desc']}\n"
        f"• Pattern: {r['pattern']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {r['time']} | T.TIME: 1 MINUTE\n"
        f"⚡ Signal valid for next 1-2 minutes\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Trade at your own risk</i>"
    )

def send_signals():
    for pair_name, symbol in PAIRS.items():
        try:
            result = analyze(pair_name, symbol)
            if result:
                send_message(format_signal(result))
                time.sleep(3)
        except:
            pass

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
            input_pair = parts[1].upper().replace("OTC", "").strip() if len(parts) > 1 else "EURUSD"
            if "/" not in input_pair and len(input_pair) == 6:
                input_pair = input_pair[:3] + "/" + input_pair[3:]
            matched = "EUR/USD"
            matched_symbol = "EURUSD=X"
            for pair_name, symbol in PAIRS.items():
                if input_pair.replace("/", "") in pair_name.replace("/", ""):
                    matched = pair_name
                    matched_symbol = symbol
                    break
            send_message(f"🔎 Analyzing {matched}... please wait.")
            result = analyze(matched, matched_symbol)
            if result:
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": format_signal(result), "parse_mode": "HTML"}
                )
            else:
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": f"🔍 No clear signal for {matched} right now. Market is ranging — wait for a stronger setup.", "parse_mode": "HTML"}
                )

        elif text == "/pairs":
            pair_list = "\n".join([f"• {p}" for p in PAIRS.keys()])
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": f"📊 <b>Monitored Pairs:</b>\n{pair_list}\n\nUse /analyze EURUSD to check any pair.", "parse_mode": "HTML"}
            )

        elif text == "/start":
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": (
                    "🚀 <b>FRX Signal Box PRO</b>\n\n"
                    "📊 <b>Commands:</b>\n"
                    "/analyze EURUSD\n"
                    "/analyze GBPUSD\n"
                    "/analyze USDJPY\n"
                    "/pairs - all pairs\n\n"
                    "⭐ <b>Grade System:</b>\n"
                    "A = 70%+ confidence\n"
                    "B = 55-69% confidence\n"
                    "C = below 55%\n\n"
                    "⚡ Auto signals every 5 minutes!"
                ), "parse_mode": "HTML"}
            )
    except:
        pass

send_message("✅ <b>FRX Signal Box PRO - Updated!</b>\nSignal threshold lowered for more frequent alerts.\nAuto signals every 5 minutes!")

counter = 0
while True:
    handle_commands()
    if counter % 30 == 0:
        send_signals()
    counter += 1
    time.sleep(10)
