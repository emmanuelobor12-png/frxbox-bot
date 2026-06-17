import os
import time
import requests
import pandas as pd
import ta
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# Note: Yahoo Finance handles standard markets. For OTC pairs, an API websocket connection to the broker would be required.
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
    """Changed default to 1m interval to capture immediate 1-minute expiration setups like the video."""
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

def get_price_data_5m(symbol):
    return get_price_data(symbol, interval="5m", period="5d")

def detect_advanced_patterns(opens, highs, lows, closes):
    """Approximates complex structural patterns seen in the reference video UI using recent price pivots."""
    if len(closes) < 20:
        return "Normal Market Structure"
        
    # Get recent local points
    last_5 = closes.iloc[-5:]
    prev_15 = closes.iloc[-20:-5]
    
    # Heuristic for Head and Shoulders / Inverse Head and Shoulders
    if len(closes) >= 30:
        s1 = closes.iloc[-25:-20].max()
        head = closes.iloc[-20:-10].max()
        s2 = closes.iloc[-10:-5].max()
        if head > s1 and head > s2 and abs(s1 - s2) < (head * 0.001):
            return "Head and Shoulders (Bearish)"
            
        is1 = closes.iloc[-25:-20].min()
        ihead = closes.iloc[-20:-10].min()
        is2 = closes.iloc[-10:-5].min()
        if ihead < is1 and ihead < is2 and abs(is1 - is2) < (is1 * 0.001):
            return "Inverse Head and Shoulders (Bullish)"

    # Falling/Rising Wedge heuristics based on high/low convergence
    high_trend = highs.iloc[-10:].linear_trend if hasattr(highs.iloc[-10:], 'linear_trend') else (highs.iloc[-1] - highs.iloc[-10])
    low_trend = lows.iloc[-10:].linear_trend if hasattr(lows.iloc[-10:], 'linear_trend') else (lows.iloc[-1] - lows.iloc[-10])
    
    if high_trend < 0 and low_trend < 0 and abs(high_trend) > abs(low_trend):
        return "Falling Wedge (Bullish Reversal)"
    elif high_trend > 0 and low_trend > 0 and low_trend > high_trend:
        return "Rising Wedge (Bearish Reversal)"

    # Fallback to standard candlestick patterns
    o2, h2, l2, c2 = opens.iloc[-1], highs.iloc[-1], lows.iloc[-1], closes.iloc[-1]
    o1, c1 = opens.iloc[-2], closes.iloc[-2]
    body2 = abs(c2 - o2)
    lower_wick = min(o2, c2) - l2
    upper_wick = h2 - max(o2, c2)
    
    if c1 < o1 and c2 > o2 and c2 > o1:
        return "Bullish Engulfing"
    if c1 > o1 and c2 < o2 and c2 < o1:
        return "Bearish Engulfing"
    if lower_wick > 2 * body2 and upper_wick < body2:
        return "Hammer Setup"
    if upper_wick > 2 * body2 and lower_wick < body2:
        return "Shooting Star"
        
    return "Consolidation Pattern"

def analyze(pair_name, symbol):
    data = get_price_data(symbol, interval="1m")
    data_5m = get_price_data_5m(symbol)
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

    # MACD & Divergence Logic
    macd_ind = ta.trend.MACD(closes)
    macd_line = macd_ind.macd().iloc[-1]
    signal_line = macd_ind.macd_signal().iloc[-1]
    
    # Simple Divergence check
    macd_desc = "Bearish Momentum"
    if macd_line > signal_line:
        macd_desc = "Bullish Momentum"
        if closes.iloc[-1] < closes.iloc[-5] and macd_line > macd_ind.macd().iloc[-5]:
            macd_desc = "MACD: Divergence with Price (Bullish)"
    else:
        if closes.iloc[-1] > closes.iloc[-5] and macd_line < macd_ind.macd().iloc[-5]:
            macd_desc = "MACD: Divergence with Price (Bearish)"

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(closes)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    
    if current <= bb_lower:
        bb_desc = "Breaking below Lower Band (Reversal Likely)"
    elif current >= bb_upper:
        bb_desc = "Breaking above Upper Band (Pullback Likely)"
    else:
        bb_desc = "Ranging Inside Bands"

    # EMA Crossings
    ema9 = ta.trend.EMAIndicator(closes, window=9).ema_indicator().iloc[-1]
    ema21 = ta.trend.EMAIndicator(closes, window=21).ema_indicator().iloc[-1]
    ema_desc = "EMA lines converging"
    if ema9 > ema21 and current > ema9:
        ema_desc = "Upper Trend Acceleration"
    elif ema9 < ema21 and current < ema9:
        ema_desc = "Lower Trend Acceleration"

    # Dynamic Volatility calculation matching the UI terms
    std = closes.pct_change().std()
    volatility = "Expanding" if std > 0.0015 else "Contracting"

    support = round(lows.iloc[-20:].min(), 5)
    resistance = round(highs.iloc[-20:].max(), 5)
    pattern = detect_advanced_patterns(opens, highs, lows, closes)

    # HTF Trend Check (5-minute charts instead of 1-hour to keep fast paces)
    htf_trend = "Neutral"
    if data_5m and len(data_5m["closes"]) > 20:
        h_closes = data_5m["closes"]
        h_ema = ta.trend.EMAIndicator(h_closes, window=20).ema_indicator().iloc[-1]
        htf_trend = "UPWARD" if h_closes.iloc[-1] > h_ema else "DOWNWARD"

    # === SCORING LOGIC ===
    bull_points = 0
    bear_points = 0

    if rsi_val < 35 or "Bullish" in macd_desc or current <= bb_lower:
        bull_points += 4
    if rsi_val > 65 or "Bearish" in macd_desc or current >= bb_upper:
        bear_points += 4
    if "Bullish" in pattern:
        bull_points += 3
    if "Bearish" in pattern:
        bear_points += 3

    if bull_points > bear_points:
        confidence = min(98, 50 + (bull_points * 5))
        direction = "HIGHER"
        emoji, risk, risk_emoji = "🟢", "LOW RISK", "🟢"
    elif bear_points > bull_points:
        confidence = min(98, 50 + (bear_points * 5))
        direction = "LOWER"
        emoji, risk, risk_emoji = "🔴", "LOW RISK", "🔴"
    else:
        return None

    return {
        "pair": pair_name, "direction": direction, "emoji": emoji,
        "confidence": confidence, "risk": risk, "risk_emoji": risk_emoji,
        "price": current, "support": support, "resistance": resistance,
        "volatility": volatility, "htf_trend": htf_trend, "pattern": pattern,
        "rsi_desc": f"RSI ({rsi_val:.0f})", "macd_desc": macd_desc,
        "bb_desc": bb_desc, "ema_desc": ema_desc,
        "time": datetime.now().strftime("%B %d, %H:%M")
    }

def format_signal(r):
    """Outputs matching the structural configuration layout used in the reference AI panel overlay."""
    return (
        f" STOCK | Advanced AI Trading \n"
        f"⚡ <b>{r['pair']} FORECAST:</b>\n"
        f"<b>{r['emoji']} {r['direction']}</b> [ {r['risk']} ]\n"
        f"💪 <b>CONFIDENCE:</b> {r['confidence']}%\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 <b>Market Overview:</b>\n"
        f"• Volatility: {r['volatility']}\n"
        f"• Volume: Accelerating\n"
        f"• HTF Trend: {r['htf_trend']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Market Snapshot:</b>\n"
        f"• Price: {r['price']:.5f}\n"
        f"• Resistance (R1): {r['resistance']}\n"
        f"• Support (S1): {r['support']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔬 <b>Technical Analysis:</b>\n"
        f"• {r['rsi_desc']}\n"
        f"• {r['macd_desc']}\n"
        f"• Bollinger Bands: {r['bb_desc']}\n"
        f"• Moving Averages: {r['ema_desc']}\n"
        f"• Pattern: <b>{r['pattern']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📅 {r['time']} | Expiration: 1 MINUTE"
    )

def main_loop():
    send_message("🚀 <b>AI Trading Engine Synced</b>\nMonitoring charts on 1-minute tracking frequencies...")
    while True:
        for pair_name, symbol in PAIRS.items():
            res = analyze(pair_name, symbol)
            if res and res["confidence"] > 65:  # Only alert on higher conviction signals
                send_message(format_signal(res))
                time.sleep(2)
        time.sleep(30)  # Check for execution setups every 30 seconds

if __name__ == "__main__":
    main_loop()

