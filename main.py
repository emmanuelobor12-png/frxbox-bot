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

def get_price_data(symbol, interval="1m", period="1d"):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        result = data["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        closes  = pd.Series([c for c in quote["close"]  if c is not None])
        highs   = pd.Series([h for h in quote["high"]   if h is not None])
        lows    = pd.Series([l for l in quote["low"]    if l is not None])
        opens   = pd.Series([o for o in quote["open"]   if o is not None])
        volumes = pd.Series([v for v in quote["volume"] if v is not None])
        return {"closes": closes, "highs": highs, "lows": lows, "opens": opens, "volumes": volumes}
    except:
        return None

def get_price_data_5m(symbol):
    return get_price_data(symbol, interval="5m", period="5d")

# ── REAL VOLUME ANALYSIS ──────────────────────────────────────────────────────
def get_volume_description(volumes):
    """Compare recent volume to average to give a real volume reading."""
    if len(volumes) < 10:
        return "Volume: Insufficient Data"
    avg_vol = volumes.iloc[-20:].mean() if len(volumes) >= 20 else volumes.mean()
    recent_vol = volumes.iloc[-3:].mean()
    ratio = recent_vol / avg_vol if avg_vol > 0 else 1

    if ratio >= 1.5:
        return "Above Average (Strong Move Possible)"
    elif ratio >= 1.1:
        return "Slightly Above Average"
    elif ratio <= 0.6:
        return "Well Below Average (Weak Signal)"
    elif ratio <= 0.9:
        return "Below Average"
    else:
        return "Average (Normal Conditions)"

# ── REAL RISK LEVEL ───────────────────────────────────────────────────────────
def get_risk_level(volatility, volumes, confidence, htf_trend, direction):
    """
    Risk is HIGH when:
      - Volatility is expanding (erratic price moves)
      - Volume is weak (signal not backed by participation)
      - HTF trend opposes our direction
    Risk is LOW only when all three align well.
    """
    risk_points = 0

    if volatility == "Expanding":
        risk_points += 1
    if "Below" in get_volume_description(volumes) or "Weak" in get_volume_description(volumes):
        risk_points += 1
    if (direction == "HIGHER" and htf_trend == "DOWNWARD") or \
       (direction == "LOWER"  and htf_trend == "UPWARD"):
        risk_points += 2  # Counter-trend trades carry higher risk

    if risk_points == 0:
        return "LOW RISK", "🟢"
    elif risk_points <= 2:
        return "MEDIUM RISK", "🟡"
    else:
        return "HIGH RISK", "🔴"

# ── PATTERN DETECTION ─────────────────────────────────────────────────────────
def detect_advanced_patterns(opens, highs, lows, closes):
    if len(closes) < 20:
        return "Normal Market Structure"

    if len(closes) >= 30:
        s1   = closes.iloc[-25:-20].max()
        head = closes.iloc[-20:-10].max()
        s2   = closes.iloc[-10:-5].max()
        if head > s1 and head > s2 and abs(s1 - s2) < (head * 0.001):
            return "Head and Shoulders (Bearish)"

        is1   = closes.iloc[-25:-20].min()
        ihead = closes.iloc[-20:-10].min()
        is2   = closes.iloc[-10:-5].min()
        if ihead < is1 and ihead < is2 and abs(is1 - is2) < (is1 * 0.001):
            return "Inverse Head and Shoulders (Bullish)"

    high_trend = highs.iloc[-1] - highs.iloc[-10]
    low_trend  = lows.iloc[-1]  - lows.iloc[-10]

    if high_trend < 0 and low_trend < 0 and abs(high_trend) > abs(low_trend):
        return "Falling Wedge (Bullish Reversal)"
    elif high_trend > 0 and low_trend > 0 and low_trend > high_trend:
        return "Rising Wedge (Bearish Reversal)"

    o2, h2, l2, c2 = opens.iloc[-1], highs.iloc[-1], lows.iloc[-1], closes.iloc[-1]
    o1, c1 = opens.iloc[-2], closes.iloc[-2]
    body2       = abs(c2 - o2)
    lower_wick  = min(o2, c2) - l2
    upper_wick  = h2 - max(o2, c2)

    if c1 < o1 and c2 > o2 and c2 > o1:
        return "Bullish Engulfing"
    if c1 > o1 and c2 < o2 and c2 < o1:
        return "Bearish Engulfing"
    if lower_wick > 2 * body2 and upper_wick < body2:
        return "Hammer Setup"
    if upper_wick > 2 * body2 and lower_wick < body2:
        return "Shooting Star"

    return "Consolidation Pattern"

# ── MAIN ANALYSIS ─────────────────────────────────────────────────────────────
def analyze(pair_name, symbol):
    data    = get_price_data(symbol, interval="1m")
    data_5m = get_price_data_5m(symbol)
    if data is None or len(data["closes"]) < 30:
        return None

    closes  = data["closes"]
    highs   = data["highs"]
    lows    = data["lows"]
    opens   = data["opens"]
    volumes = data["volumes"]
    current = closes.iloc[-1]

    # RSI
    rsi_val = ta.momentum.RSIIndicator(closes, window=14).rsi().iloc[-1]

    # MACD
    macd_ind    = ta.trend.MACD(closes)
    macd_line   = macd_ind.macd().iloc[-1]
    signal_line = macd_ind.macd_signal().iloc[-1]
    macd_desc   = "Bearish Momentum"
    if macd_line > signal_line:
        macd_desc = "Bullish Momentum"
        if closes.iloc[-1] < closes.iloc[-5] and macd_line > macd_ind.macd().iloc[-5]:
            macd_desc = "Bullish Divergence Detected"
    else:
        if closes.iloc[-1] > closes.iloc[-5] and macd_line < macd_ind.macd().iloc[-5]:
            macd_desc = "Bearish Divergence Detected"

    # Bollinger Bands
    bb       = ta.volatility.BollingerBands(closes)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    if current <= bb_lower:
        bb_desc = "Below Lower Band — Reversal Likely"
    elif current >= bb_upper:
        bb_desc = "Above Upper Band — Pullback Likely"
    else:
        bb_desc = "Ranging Inside Bands"

    # EMA
    ema9  = ta.trend.EMAIndicator(closes, window=9).ema_indicator().iloc[-1]
    ema21 = ta.trend.EMAIndicator(closes, window=21).ema_indicator().iloc[-1]
    if ema9 > ema21 and current > ema9:
        ema_desc = "Uptrend — EMA9 above EMA21"
    elif ema9 < ema21 and current < ema9:
        ema_desc = "Downtrend — EMA9 below EMA21"
    else:
        ema_desc = "EMAs Converging — No Clear Trend"

    # Volatility
    std        = closes.pct_change().std()
    volatility = "Expanding" if std > 0.0015 else "Contracting"

    support    = round(lows.iloc[-20:].min(), 5)
    resistance = round(highs.iloc[-20:].max(), 5)
    pattern    = detect_advanced_patterns(opens, highs, lows, closes)

    # HTF Trend (5m)
    htf_trend = "Neutral"
    if data_5m and len(data_5m["closes"]) > 20:
        h_closes  = data_5m["closes"]
        h_ema     = ta.trend.EMAIndicator(h_closes, window=20).ema_indicator().iloc[-1]
        htf_trend = "UPWARD ↑" if h_closes.iloc[-1] > h_ema else "DOWNWARD ↓"

    # Volume (REAL)
    volume_desc = get_volume_description(volumes)

    # ── SCORING ──
    bull_points = 0
    bear_points = 0

    if rsi_val < 35:
        bull_points += 2
    if rsi_val > 65:
        bear_points += 2
    if "Bullish" in macd_desc:
        bull_points += 2
    if "Bearish" in macd_desc:
        bear_points += 2
    if current <= bb_lower:
        bull_points += 2
    if current >= bb_upper:
        bear_points += 2
    if "Bullish" in pattern:
        bull_points += 3
    if "Bearish" in pattern:
        bear_points += 3
    if htf_trend == "UPWARD ↑":
        bull_points += 2
    if htf_trend == "DOWNWARD ↓":
        bear_points += 2

    if bull_points > bear_points:
        total      = bull_points + bear_points
        confidence = min(95, 50 + int((bull_points / total) * 50)) if total > 0 else 50
        direction  = "HIGHER"
        emoji      = "🟢"
    elif bear_points > bull_points:
        total      = bull_points + bear_points
        confidence = min(95, 50 + int((bear_points / total) * 50)) if total > 0 else 50
        direction  = "LOWER"
        emoji      = "🔴"
    else:
        return None

    risk, risk_emoji = get_risk_level(volatility, volumes, confidence, htf_trend, direction)

    # Only return HIGH confidence signals
    if confidence < 80:
        return None

    return {
        "pair": pair_name, "direction": direction, "emoji": emoji,
        "confidence": confidence, "risk": risk, "risk_emoji": risk_emoji,
        "price": current, "support": support, "resistance": resistance,
        "volatility": volatility, "htf_trend": htf_trend, "pattern": pattern,
        "volume_desc": volume_desc,
        "rsi_val": rsi_val,
        "macd_desc": macd_desc,
        "bb_desc": bb_desc, "ema_desc": ema_desc,
        "time": datetime.now().strftime("%B %d, %H:%M")
    }

# ── SIGNAL FORMATTER ──────────────────────────────────────────────────────────
def format_signal(r):
    rsi_read = (
        "Oversold — Buy Pressure" if r['rsi_val'] < 35
        else "Overbought — Sell Pressure" if r['rsi_val'] > 65
        else "Neutral Zone"
    )
    skip_warning = ""
    if r["risk"] == "HIGH RISK":
        skip_warning = "⚠️ <b>Consider skipping — High Risk</b>\n"
    elif "Below" in r["volume_desc"] or "Weak" in r["volume_desc"]:
        skip_warning = "⚠️ <b>Weak volume — trade carefully</b>\n"

    return (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 <b>{r['pair']}</b>  |  {r['time']}  |  ⏱ 1 MIN\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{r['emoji']} <b>{r['direction']}</b>  |  💵 {r['price']:.5f}\n"
        f"\n"
        f"💪 Confidence:  <b>{r['confidence']}%</b>\n"
        f"🔭 HTF Trend:   <b>{r['htf_trend']}</b>\n"
        f"{r['risk_emoji']} Risk:          <b>{r['risk']}</b>\n"
        f"📦 Volume:      <b>{r['volume_desc'].split('(')[0].strip()}</b>\n"
        f"\n"
        f"{skip_warning}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 RSI ({r['rsi_val']:.0f}) — {rsi_read}\n"
        f"⚡ MACD — {r['macd_desc']}\n"
        f"🎯 BB — {r['bb_desc']}\n"
        f"🕯 Pattern — <b>{r['pattern']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔴 R1: {r['resistance']}   🟢 S1: {r['support']}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
def main_loop():
    send_message(
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🚀  <b>AI Trading Engine Online</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Monitoring 10 pairs on 1-minute charts.\n"
        "Signals will only appear when confidence ≥ 80%.\n\n"
        "🟢 LOW RISK = best trades\n"
        "🟡 MEDIUM RISK = trade carefully\n"
        "🔴 HIGH RISK = consider skipping\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    while True:
        for pair_name, symbol in PAIRS.items():
            res = analyze(pair_name, symbol)
            if res:
                send_message(format_signal(res))
                time.sleep(3)
        time.sleep(30)

if __name__ == "__main__":
    main_loop()

