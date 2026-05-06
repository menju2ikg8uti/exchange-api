import time
import requests
import websocket
import json
import os
import hmac
import hashlib
import threading
import re
from dotenv import load_dotenv
from decimal import Decimal, getcontext, ROUND_DOWN

# ================= CONFIG =================
getcontext().prec = 28

load_dotenv()
API_KEY = os.getenv("MEXC_API_KEY") or ""
API_SECRET = os.getenv("MEXC_SECRET_KEY") or ""

BASE_URL = "https://api.mexc.com"
WS_URL = "wss://wbs-api.mexc.com/ws"

SYMBOL = "BTCUSDT"

DROP_PERCENT = Decimal("0.0003")
BOUNCE_PERCENT = Decimal("0.00005")

PROFIT_PERCENT = Decimal("0.0003")
PULLBACK_PERCENT = Decimal("0.00015")
SELL_BOUNCE = Decimal("0.00005")

MAX_PRICE_CHANGE = Decimal("0.01")  # 1%

# ================= GLOBAL =================
last_price = Decimal("0")
last_valid_price = Decimal("0")

balance = {"BTC": Decimal("0"), "USDT": Decimal("0")}

ws_lock = threading.Lock()
ws_active = False

price_pattern = re.compile(rb'\d+\.\d+')

step_size = Decimal("0.000001")
min_notional = Decimal("5")

# ================= UTILS =================
def sign(params):
    query = "&".join([f"{k}={params[k]}" for k in params])
    return hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()

def send_order(params):
    params["timestamp"] = int(time.time() * 1000)
    params["signature"] = sign(params)
    headers = {"X-MEXC-APIKEY": API_KEY}
    res = requests.post(BASE_URL + "/api/v3/order", params=params, headers=headers)
    return res.json()

def adjust(value, step):
    return (value // step) * step

# ================= BALANCE =================
def get_balance():
    global balance

    params = {"timestamp": int(time.time() * 1000)}
    params["signature"] = sign(params)

    headers = {"X-MEXC-APIKEY": API_KEY}
    res = requests.get(BASE_URL + "/api/v3/account", params=params, headers=headers)
    data = res.json()

    for asset in data.get("balances", []):
        if asset["asset"] == "BTC":
            balance["BTC"] = Decimal(asset["free"])
        elif asset["asset"] == "USDT":
            balance["USDT"] = Decimal(asset["free"])

    print("[BALANCE]", balance)

# ================= ORDER =================
def buy_market_all():
    usdt = balance["USDT"]

    if usdt < min_notional or last_price == 0:
        return None

    qty = adjust(usdt / last_price, step_size)

    if qty <= 0:
        return None

    qty = qty.quantize(step_size, rounding=ROUND_DOWN)

    print("[BUY]", qty)

    res = send_order({
        "symbol": SYMBOL,
        "side": "BUY",
        "type": "MARKET",
        "quantity": str(qty)
    })

    print(res)
    return res if "orderId" in res else None

def sell_market_all():
    btc = adjust(balance["BTC"], step_size)

    if btc <= 0:
        return None

    btc = btc.quantize(step_size, rounding=ROUND_DOWN)

    print("[SELL]", btc)

    res = send_order({
        "symbol": SYMBOL,
        "side": "SELL",
        "type": "MARKET",
        "quantity": str(btc)
    })

    print(res)
    return res

# ================= PRICE =================
def extract_price(message):
    if isinstance(message, bytes):
        m = price_pattern.findall(message)
        if m:
            return Decimal(m[0].decode())
    return None

def is_valid_price(new_price):
    global last_valid_price

    if last_valid_price == 0:
        last_valid_price = new_price
        return True

    change = abs(new_price - last_valid_price) / last_valid_price

    if change > MAX_PRICE_CHANGE:
        print(f"[SKIP SPIKE] {new_price} change {(change*100):.2f}%")
        return False

    last_valid_price = new_price
    return True

# ================= SAFE WS =================
def run_ws_until(trigger_func):
    global ws_active, last_price

    done = threading.Event()

    def on_message(ws, msg):
        global last_price

        price = extract_price(msg)
        if not price:
            return

        if not is_valid_price(price):
            return

        last_price = price

        if trigger_func(price):
            done.set()
            ws.close()

    def on_open(ws):
        ws.send(json.dumps({
            "method": "SUBSCRIPTION",
            "params": [
                "spot@public.miniTicker.v3.api.pb@BTCUSDT@UTC+8"
            ]
        }))

    def on_close(ws, *args):
        done.set()

    with ws_lock:
        if ws_active:
            return
        ws_active = True

    ws = websocket.WebSocketApp(
        WS_URL,
        on_message=on_message,
        on_open=on_open,
        on_close=on_close
    )

    try:
        ws.run_forever()
    except KeyboardInterrupt:
        ws.close()
        raise

    done.wait()

    with ws_lock:
        ws_active = False

# ================= BUY LOGIC =================
def wait_buy_signal():
    highest = Decimal("0")
    lowest = Decimal("0")
    state = "DROP"

    def logic(price):
        nonlocal highest, lowest, state

        if highest == 0:
            highest = price

        if state == "DROP":
            if price > highest:
                highest = price

            drop = (highest - price) / highest
            print(f"[BUY DROP] {price} {(drop*100):.4f}%")

            if drop >= DROP_PERCENT:
                lowest = price
                state = "BOUNCE"

        elif state == "BOUNCE":
            if price < lowest:
                lowest = price

            bounce = (price - lowest) / lowest
            print(f"[BUY BOUNCE] {price} {(bounce*100):.4f}%")

            if bounce >= BOUNCE_PERCENT:
                print("[BUY SIGNAL]")
                return True

        return False

    run_ws_until(logic)

# ================= SELL LOGIC =================
def wait_sell_signal(entry_price):
    highest = entry_price
    lowest = Decimal("0")
    state = "PROFIT"

    def logic(price):
        nonlocal highest, lowest, state

        profit = (price - entry_price) / entry_price

        if state == "PROFIT":
            if price > highest:
                highest = price

            print(f"[SELL PROFIT] {price} {(profit*100):.4f}%")

            if profit >= PROFIT_PERCENT:
                state = "PULLBACK"

        elif state == "PULLBACK":
            if price > highest:
                highest = price

            pullback = (highest - price) / highest
            print(f"[SELL PULLBACK] {price} {(pullback*100):.4f}% profit: {(profit*100):.4f}%")

            if pullback >= PULLBACK_PERCENT:
                lowest = price
                state = "BOUNCE"

        elif state == "BOUNCE":
            if price < lowest:
                lowest = price

            bounce = (price - lowest) / lowest
            print(f"[SELL BOUNCE] {price} {(bounce*100):.4f}% profit: {(profit*100):.4f}%")

            if bounce >= SELL_BOUNCE:
                print("[SELL SIGNAL]")
                return True

        return False

    run_ws_until(logic)

# ================= RUN =================
if __name__ == "__main__":
    try:
        print("\n=== START ===")

        get_balance()

        # ===== BUY =====
        wait_buy_signal()

        if buy_market_all():
            get_balance()
            entry = last_price

            # ===== SELL =====
            wait_sell_signal(entry)
            sell_market_all()

        print("\n=== DONE ===")

    except KeyboardInterrupt:
        print("\n[EXIT] Dihentikan manual")
