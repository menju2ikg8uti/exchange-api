import json
import websocket

BASE_URL = 'wss://wbs-api.mexc.com/ws'

def on_message(ws, message):
    print(message)

def on_error(ws, error):
    print(error)

def on_close(ws):
    print("Connection closed ....")

def on_open(ws):
    subscribe_message = {
            "method": "SUBSCRIPTION",
            "params": [
                "spot@public.aggre.deals.v3.api.pb@10ms@BTCUSDT"

            ]
        }
    ws.send(json.dumps(subscribe_message))
    logger.info(f"Sent subscription message: {subscribe_message}")


if __name__ == "__main__":
    websocket.enableTrace(False)
    ws = websocket.WebSocketApp(BASE_URL,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close,
                                )
    ws.on_open = on_open
    ws.run_forever()
