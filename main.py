import time
import hmac
import hashlib
import requests
import os
from datetime import datetime, timedelta

API_KEY = os.getenv("MEXC_API_KEY")
SECRET_KEY = os.getenv("MEXC_SECRET_KEY")

BASE_URL = "https://api.mexc.com"
LOG_FILE = "usdt_log.txt"

def get_account_info():
    endpoint = "/api/v3/account"
    timestamp = int(time.time() * 1000)

    query_string = f"timestamp={timestamp}"

    signature = hmac.new(
        SECRET_KEY.encode(),
        query_string.encode(),
        hashlib.sha256
    ).hexdigest()

    url = f"{BASE_URL}{endpoint}?{query_string}&signature={signature}"

    headers = {
        "X-MEXC-APIKEY": API_KEY
    }

    response = requests.get(url, headers=headers)
    return response.json()

def get_usdt_balance():
    data = get_account_info()

    if "balances" not in data:
        print("Error:", data)
        return None

    for asset in data["balances"]:
        if asset["asset"] == "USDT":
            free = float(asset["free"])
            locked = float(asset["locked"])
            total = free + locked

            if total < 10:
                print(f"USDT terlalu kecil: {total:.4f} → skip")
                return None

            return round(total, 4)

    return None

def read_log():
    if not os.path.exists(LOG_FILE):
        return []

    with open(LOG_FILE, "r") as f:
        lines = [line.strip() for line in f if line.strip()]
    return lines

def write_log(lines):
    with open(LOG_FILE, "w") as f:
        for line in lines:
            f.write(line + "\n")

def parse_datetime(timestamp_str, last_date):
    # FULL FORMAT
    if len(timestamp_str) > 5:
        dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M")
        return dt, dt.strftime("%Y-%m-%d")

    # ONLY TIME → pakai tanggal sebelumnya
    if last_date is None:
        raise ValueError("Format error: time tanpa tanggal di baris awal")

    dt = datetime.strptime(f"{last_date} {timestamp_str}", "%Y-%m-%d %H:%M")
    return dt, last_date

def format_lines(lines):
    formatted = []
    last_date = None

    for line in lines:
        timestamp_str, value = line.split(" | ")

        dt, current_date = parse_datetime(timestamp_str, last_date)

        if current_date == last_date:
            new_time = dt.strftime("%H:%M")
        else:
            new_time = dt.strftime("%Y-%m-%d %H:%M")

        formatted.append(f"{new_time} | {value}")
        last_date = current_date

    return formatted

def update_log(new_value):
    now = datetime.utcnow() + timedelta(hours=7)
    timestamp = now.strftime("%Y-%m-%d %H:%M")

    lines = read_log()

    # ===== CEK DUPLIKAT =====
    if lines:
        last_value = lines[-1].split(" | ")[-1]
        if last_value == f"{new_value:.4f}":
            print("Duplicate → skip log")
            return

    # ===== TAMBAH DATA =====
    lines.append(f"{timestamp} | {new_value:.4f}")

    # ===== FORMAT ULANG =====
    formatted_lines = format_lines(lines)

    write_log(formatted_lines)
    print("Logged & formatted")

def main():
    balance = get_usdt_balance()

    if balance is None:
        return

    update_log(balance)

if __name__ == "__main__":
    main()
