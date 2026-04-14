import time
import hmac
import hashlib
import requests
import os
from datetime import datetime

API_KEY = os.getenv("MEXC_API_KEY")
SECRET_KEY = os.getenv("MEXC_SECRET_KEY")

BASE_URL = "https://api.mexc.com"
LOG_FILE = "usdt_log.txt"

RESET_HOUR = 8  # jam 08:00 pagi

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

def is_reset_time():
    now = datetime.now()
    return now.hour == RESET_HOUR and now.minute < 10  # toleransi cron 10 menit

def update_log(new_value):
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    lines = read_log()

    # ===== RESET LOG SETIAP HARI JAM 08:00 =====
    if is_reset_time():
        if lines:
            first_line_date = lines[0].split(" ")[0]
            today_date = now.strftime("%Y-%m-%d")

            # kalau file bukan hari ini → reset
            if first_line_date != today_date:
                print("Reset log harian")
                lines = []

    # ===== CEK DUPLIKAT (berdasarkan nilai terakhir) =====
    if lines:
        last_value = lines[-1].split(" | ")[-1]
        if last_value == f"{new_value:.4f}":
            print("Duplicate → skip log")
            return

    # ===== FORMAT: tanggal jam | saldo =====
    new_line = f"{timestamp} | {new_value:.4f}"
    lines.append(new_line)

    write_log(lines)
    print(f"Logged: {new_line}")

def main():
    balance = get_usdt_balance()

    if balance is None:
        return

    update_log(balance)

if __name__ == "__main__":
    main()
