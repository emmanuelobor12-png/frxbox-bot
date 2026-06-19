import os
import time
import requests
import pandas as pd
import ta
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID   = os.environ.get("CHAT_ID")

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

def get_updates(offset=None):
    """Poll Telegram for new messages sent to the bot (used for on-demand /check commands)."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 10}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(url, params=params, timeout=15)
        return r.json().get("result", [])
    except:
        return []

def normalize_pair_input(text):
    """Turns things like 'eurusd', 'EUR/USD', 'eur usd' into a PAIRS key, or None if not found."""
    cleaned = text.upper().replace("/", "").replace(" ", "").replace("-", "")
    for name in PAIRS:
        if name.upper().replace("/", "") == cleaned:
            return name
    return None

def get_price_data(symbol, interval="1m", period="1d"):
    try:
        url  = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
        r    = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        result = data["chart"]["result"][0]
        quote  = result["indicators"]["quote"][0]
        closes  = pd.Series([c for c in quote["close"]  if c is not None])
        highs   = pd.Series([h for h in quote["high"]   if h is not None])
        lows    = pd.Series([l for l in quote["low"]    if l is not None])
        opens   = pd.Series([o for o in quote["open"]   if o is not None])
        volumes = pd.Series([v for v in quote["volume"] if v is not None])
        if len(closes) < 50:
            return None
        return {"closes": closes, "highs": highs, "lows": lows, "opens": opens, "volumes": volumes}
    except:
        return None

def get_price_data_5m(symbol):
    return get_price_data(symbol, interval="5m", period="5d")

# ── VOLUME ────────────────────────────────────────────────────────────────────
def get_volume_description(volumes):
    if len(volumes) < 20:
        return "Insufficient Data", False
    avg_vol    = volumes.iloc[-20:].mean()
    recent_vol = volumes.iloc[-3:].mean()
    ratio      = recent_vol / avg_vol if avg_vol > 0 else 1
    if ratio >= 1.5:
        return "Above Average", True
    elif ratio >= 1.1:
        return "Slightly Above Average", True
    elif ratio <= 0.6:
        return "Well Below Average", False
    elif ratio <= 0.9:
        return "Below Average", False
    else:
        return "Average", True   # Average is acceptable, not a disqualifier

# ── PATTERN DETECTION ─────────────────────────────────────────────────────────
def detect_pattern(opens, highs, lows, closes):
    if len(closes) < 30:
        return "Consolidation"

    # Head and Shoulders
    s1   = closes.iloc[-25:-20].max()
    head = closes.iloc[-20:-10].max()
    s2   = closes.iloc[-10:-5].max()
    if head > s1 and head > s2 and abs(s1 - s2) < (head * 0.0015):
        return "Head and Shoulders (Bearish)"

    # Inverse Head and Shoulders
    is1   = closes.iloc[-25:-20].min()
    ihead = closes.iloc[-20:-10].min()
    is2   = closes.iloc[-10:-5].min()
    if ihead < is1 and ihead < is2 and abs(is1 - is2) < (is1 * 0.0015):
        return "Inverse Head and Shoulders (Bullish)"

    # Wedges — require at least 3 points converging
    high_trend = highs.iloc[-1] - highs.iloc[-10]
    low_trend  = lows.iloc[-1]  - lows.iloc[-10]
    if high_trend < 0 and low_trend < 0 and abs(high_trend) > abs(low_trend) * 1.2:
        return "Falling Wedge (Bullish)"
    if high_trend > 0 and low_trend > 0 and low_trend > high_trend * 1.2:
        return "Rising Wedge (Bearish)"

    # Candlestick patterns — require meaningful body size
    o2, h2, l2, c2 = opens.iloc[-1], highs.iloc[-1], lows.iloc[-1], closes.iloc[-1]
    o1, c1         = opens.iloc[-2], closes.iloc[-2]
    body2       = abs(c2 - o2)
    body1       = abs(c1 - o1)
    lower_wick  = min(o2, c2) - l2
    upper_wick  = h2 - max(o2, c2)
    avg_body    = closes.pct_change().abs().mean()

    # Only call engulfing if body is meaningfully large
    if body2 > body1 * 1.5 and c1 < o1 and c2 > o2 and c2 > o1:
        return "Bullish Engulfing"
    if body2 > body1 * 1.5 and c1 > o1 and c2 < o2 and c2 < o1:
        return "Bearish Engulfing"
    if lower_wick > 2.5 * body2 and upper_wick < body2 * 0.5 and body2 > 0:
        return "Hammer (Bullish)"
    if upper_wick > 2.5 * body2 and lower_wick < body2 * 0.5 and body2 > 0:
        return "Shooting Star (Bearish)"

    return "Consolidation"

# ── MAIN ANALYSIS ─────────────────────────────────────────────────────────────
def analyze(pair_name, symbol):
    data    = get_price_data(symbol, interval="1m")
    data_5m = get_price_data_5m(symbol)

    if data is None:
        return None

    closes  = data["closes"]
    highs   = data["highs"]
    lows    = data["lows"]
    opens   = data["opens"]
    volumes = data["volumes"]
    current = closes.iloc[-1]

    # ── INDICATORS ──
    rsi_val = ta.momentum.RSIIndicator(closes, window=14).rsi().iloc[-1]

    macd_ind    = ta.trend.MACD(closes, window_slow=26, window_fast=12, window_sign=9)
    macd_line   = macd_ind.macd().iloc[-1]
    macd_prev   = macd_ind.macd().iloc[-2]
    signal_line = macd_ind.macd_signal().iloc[-1]
    signal_prev = macd_ind.macd_signal().iloc[-2]
    # Require actual crossover, not just position
    macd_bull_cross = macd_prev < signal_prev and macd_line > signal_line
    macd_bear_cross = macd_prev > signal_prev and macd_line < signal_line
    macd_bull = macd_line > signal_line
    macd_bear = macd_line < signal_line

    bb       = ta.volatility.BollingerBands(closes, window=20)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    bb_mid   = bb.bollinger_mavg().iloc[-1]
    bb_width = (bb_upper - bb_lower) / bb_mid  # Band width — narrow = consolidation

    ema9  = ta.trend.EMAIndicator(closes, window=9).ema_indicator()
    ema21 = ta.trend.EMAIndicator(closes, window=21).ema_indicator()
    ema50 = ta.trend.EMAIndicator(closes, window=50).ema_indicator()
    ema9_now  = ema9.iloc[-1];  ema9_prev  = ema9.iloc[-2]
    ema21_now = ema21.iloc[-1]; ema21_prev = ema21.iloc[-2]
    ema50_now = ema50.iloc[-1]
    # Require actual EMA crossover
    ema_bull_cross = ema9_prev < ema21_prev and ema9_now > ema21_now
    ema_bear_cross = ema9_prev > ema21_prev and ema9_now < ema21_now
    ema_bull = ema9_now > ema21_now and current > ema50_now
    ema_bear = ema9_now < ema21_now and current < ema50_now

    std        = closes.pct_change().std()
    volatility = "Expanding" if std > 0.0015 else "Contracting"

    pattern     = detect_pattern(opens, highs, lows, closes)
    volume_desc, volume_ok = get_volume_description(volumes)

    # ── HTF TREND (5m) — must use both EMA and price structure ──
    htf_trend    = "Neutral"
    htf_strong   = False
    if data_5m and len(data_5m["closes"]) > 50:
        h_closes = data_5m["closes"]
        h_ema20  = ta.trend.EMAIndicator(h_closes, window=20).ema_indicator().iloc[-1]
        h_ema50  = ta.trend.EMAIndicator(h_closes, window=50).ema_indicator().iloc[-1]
        h_price  = h_closes.iloc[-1]
        if h_price > h_ema20 and h_ema20 > h_ema50:
            htf_trend  = "UPWARD ↑"
            htf_strong = True
        elif h_price < h_ema20 and h_ema20 < h_ema50:
            htf_trend  = "DOWNWARD ↓"
            htf_strong = True
        elif h_price > h_ema20:
            htf_trend = "UPWARD ↑"
        else:
            htf_trend = "DOWNWARD ↓"

    support    = round(lows.iloc[-20:].min(), 5)
    resistance = round(highs.iloc[-20:].max(), 5)

    # ── HARD FILTERS — fail any of these = no signal ──────────────────────────

    # 1. No signals during consolidation
    if pattern == "Consolidation":
        return None

    # 2. Bollinger Bands too narrow = market not moving = skip
    if bb_width < 0.0008:
        return None

    # 3. RSI must not contradict direction
    # (checked after direction is determined below, but pre-filter extreme neutrality)
    if 45 <= rsi_val <= 55:
        return None  # RSI dead center = no momentum either way

    # ── SCORING — stricter, requires confluence ───────────────────────────────
    bull_points = 0
    bear_points = 0

    # RSI — weighted by extremity
    if rsi_val < 30:
        bull_points += 3
    elif rsi_val < 40:
        bull_points += 1
    if rsi_val > 70:
        bear_points += 3
    elif rsi_val > 60:
        bear_points += 1

    # MACD — crossovers worth more than position alone
    if macd_bull_cross:
        bull_points += 3
    elif macd_bull:
        bull_points += 1
    if macd_bear_cross:
        bear_points += 3
    elif macd_bear:
        bear_points += 1

    # Bollinger Bands
    if current <= bb_lower:
        bull_points += 2
    if current >= bb_upper:
        bear_points += 2

    # EMA — crossovers worth more
    if ema_bull_cross:
        bull_points += 3
    elif ema_bull:
        bull_points += 1
    if ema_bear_cross:
        bear_points += 3
    elif ema_bear:
        bear_points += 1

    # Pattern — strong confluence bonus
    if "Bullish" in pattern or "Hammer" in pattern or "Inverse Head" in pattern:
        bull_points += 4
    if "Bearish" in pattern or "Shooting Star" in pattern or "Head and Shoulders (Bearish)" in pattern:
        bear_points += 4

    # HTF — strong trend alignment is a significant bonus
    if htf_trend == "UPWARD ↑":
        bull_points += 3 if htf_strong else 1
    if htf_trend == "DOWNWARD ↓":
        bear_points += 3 if htf_strong else 1

    # ── DIRECTION ──
    if bull_points > bear_points:
        direction = "HIGHER"
        emoji     = "🟢"
        winning   = bull_points
        losing    = bear_points
    elif bear_points > bull_points:
        direction = "LOWER"
        emoji     = "🔴"
        winning   = bear_points
        losing    = bull_points
    else:
        return None

    # ── HARD FILTER: HTF must match direction — no exceptions ──
    if direction == "HIGHER" and htf_trend == "DOWNWARD ↓":
        return None
    if direction == "LOWER"  and htf_trend == "UPWARD ↑":
        return None

    # ── HARD FILTER: RSI contradiction ──
    if rsi_val < 35 and direction == "LOWER":
        return None
    if rsi_val > 65 and direction == "HIGHER":
        return None

    # ── CONFIDENCE — based on margin of victory, not just total ──
    margin     = winning - losing
    total      = winning + losing
    base       = 60
    conf_score = base + int((margin / max(total, 1)) * 35)
    confidence = min(90, conf_score)  # Hard cap at 90 — nothing is ever 95%+

    # Require meaningful confidence
    if confidence < 75:
        return None

    # ── RISK ──
    risk_points = 0
    if volatility == "Expanding":
        risk_points += 1
    if not volume_ok:
        risk_points += 1
    if not htf_strong:
        risk_points += 1

    if risk_points == 0:
        risk, risk_emoji = "LOW RISK", "🟢"
    elif risk_points == 1:
        risk, risk_emoji = "MEDIUM RISK", "🟡"
    else:
        risk, risk_emoji = "HIGH RISK", "🔴"

    # Skip HIGH RISK signals entirely — not worth sending
    if risk == "HIGH RISK":
        return None

    return {
        "pair": pair_name, "direction": direction, "emoji": emoji,
        "confidence": confidence, "risk": risk, "risk_emoji": risk_emoji,
        "price": current, "support": support, "resistance": resistance,
        "volatility": volatility, "htf_trend": htf_trend, "pattern": pattern,
        "volume_desc": volume_desc, "rsi_val": rsi_val,
        "macd_desc": "Crossover ✓" if (macd_bull_cross or macd_bear_cross) else ("Bullish" if macd_bull else "Bearish"),
        "bb_desc": (
            "Below Lower Band — Reversal Zone" if current <= bb_lower
            else "Above Upper Band — Reversal Zone" if current >= bb_upper
            else "Inside Bands"
        ),
        "ema_desc": (
            "EMA Crossover Up ✓" if ema_bull_cross
            else "EMA Crossover Down ✓" if ema_bear_cross
            else "Uptrend Alignment" if ema_bull
            else "Downtrend Alignment"
        ),
        "time": datetime.now().strftime("%b %d, %H:%M")
    }

# ── SIGNAL FORMATTER ──────────────────────────────────────────────────────────
def format_signal(r):
    rsi_read = (
        "Oversold" if r['rsi_val'] < 30
        else "Approaching Oversold" if r['rsi_val'] < 40
        else "Overbought" if r['rsi_val'] > 70
        else "Approaching Overbought" if r['rsi_val'] > 60
        else "Neutral"
    )
    return (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 <code>{r['pair']}</code>  |  {r['time']}  |  ⏱ 1 MIN\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{r['emoji']} <b>{r['direction']}</b>  |  💵 {r['price']:.5f}\n"
        f"\n"
        f"💪 Confidence:  <b>{r['confidence']}%</b>\n"
        f"🔭 HTF Trend:   <b>{r['htf_trend']}</b>\n"
        f"{r['risk_emoji']} Risk:          <b>{r['risk']}</b>\n"
        f"📦 Volume:      <b>{r['volume_desc']}</b>\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 RSI ({r['rsi_val']:.0f}) — {rsi_read}\n"
        f"⚡ MACD — {r['macd_desc']}\n"
        f"🎯 BB — {r['bb_desc']}\n"
        f"📐 EMA — {r['ema_desc']}\n"
        f"🕯 Pattern — <b>{r['pattern']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔴 R1: {r['resistance']}   🟢 S1: {r['support']}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

# ── ON-DEMAND COMMAND HANDLING ─────────────────────────────────────────────────
def handle_command(text):
    """Handles /check <pair> and /pairs commands from Telegram."""
    text = text.strip()

    if text.lower() in ("/pairs", "/list"):
        pair_list = "\n".join(f"• <code>{p}</code>" for p in PAIRS)
        send_message(f"📋 <b>Available Pairs</b>\n\n{pair_list}\n\nUse: <code>/check EURUSD</code>")
        return

    if text.lower().startswith("/check"):
        arg = text[6:].strip()
        if not arg:
            send_message("Usage: <code>/check EURUSD</code> or <code>/check GBP/JPY</code>")
            return
        pair_name = normalize_pair_input(arg)
        if not pair_name:
            send_message(f"⚠️ Pair '{arg}' not recognized. Send /pairs to see the full list.")
            return

        send_message(f"🔍 Checking <code>{pair_name}</code>... this takes a few seconds.")
        symbol = PAIRS[pair_name]
        res = analyze(pair_name, symbol)
        if res:
            send_message(format_signal(res))
        else:
            send_message(
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📡 <code>{pair_name}</code> — No Clean Signal\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"This pair didn't pass our filters right now\n"
                f"(low confidence, consolidating, or HTF mismatch).\n"
                f"Try again in a few minutes.\n"
                f"━━━━━━━━━━━━━━━━━━"
            )

def poll_commands(offset):
    """Checks for new Telegram messages and handles any /check commands. Returns updated offset."""
    updates = get_updates(offset)
    for update in updates:
        offset = update["update_id"] + 1
        msg = update.get("message", {})
        text = msg.get("text", "")
        if text:
            handle_command(text)
    return offset

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
def main_loop():
    send_message(
        "━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>AI Trading Engine Online</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Monitoring 10 pairs on 1-minute charts.\n\n"
        "Filters active:\n"
        "✅ Confidence ≥ 75%\n"
        "✅ HTF trend must match direction\n"
        "✅ No consolidation signals\n"
        "✅ No RSI contradictions\n"
        "✅ High risk signals blocked\n"
        "✅ Narrow market signals blocked\n\n"
        "🟢 LOW RISK = best trades\n"
        "🟡 MEDIUM RISK = trade carefully\n\n"
        "📲 <b>On-demand:</b> send <code>/check EURUSD</code>\n"
        "anytime to scan a specific pair instantly.\n"
        "Send <code>/pairs</code> to see the full list.\n"
        "━━━━━━━━━━━━━━━━━━"
    )

    offset = None
    last_scan = 0
    SCAN_INTERVAL = 45

    while True:
        # Always check for on-demand commands first — fast, ~10s max wait
        offset = poll_commands(offset)

        # Run the full background scan only every SCAN_INTERVAL seconds
        if time.time() - last_scan >= SCAN_INTERVAL:
            for pair_name, symbol in PAIRS.items():
                res = analyze(pair_name, symbol)
                if res:
                    send_message(format_signal(res))
                    time.sleep(3)
                # Check for commands between each pair too, so /check feels instant
                offset = poll_commands(offset)
            last_scan = time.time()

if __name__ == "__main__":
    main_loop()
