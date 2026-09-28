import os
import requests
import time

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
CACHE = {}
CACHE_TIME = 60

COIN_MAP = {
    "btc": "bitcoin", "比特币": "bitcoin",
    "eth": "ethereum", "以太坊": "ethereum",
    "sol": "solana",
    "doge": "dogecoin", "狗狗币": "dogecoin",
    "bnb": "binancecoin", "币安币": "binancecoin",
    "xrp": "ripple", "ada": "cardano",
    "dot": "polkadot", "ltc": "litecoin",
    "usdt": "tether", "usdc": "usd-coin"
}

FIAT_MAP = {
    "usd": "USD", "美元": "USD", "美金": "USD",
    "cny": "CNY", "rmb": "CNY", "人民币": "CNY",
    "eur": "EUR", "欧元": "EUR",
    "jpy": "JPY", "日元": "JPY",
    "gbp": "GBP", "英镑": "GBP",
    "hkd": "HKD", "港币": "HKD"
}

def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": 30, "offset": offset}
    try:
        resp = requests.get(url, params=params, timeout=35)
        return resp.json()
    except Exception as e:
        print("获取更新失败:", e)
        return {}

def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("发送消息失败:", e)

def get_crypto_market_data(coin_id):
    now = time.time()
    cache_key = f"market_{coin_id}"
    if cache_key in CACHE and now - CACHE[cache_key]['time'] < CACHE_TIME:
        return CACHE[cache_key]['data']
    url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={coin_id}&price_change_percentage=24h,7d"
    try:
        resp = requests.get(url, timeout=10).json()
        if isinstance(resp, list) and len(resp) > 0:
            CACHE[cache_key] = {'data': resp[0], 'time': now}
            return resp[0]
    except Exception as e:
        print(f"查询 {coin_id} 行情失败:", e)
    return None

def get_crypto_simple_price(coin_id):
    now = time.time()
    cache_key = f"simple_{coin_id}"
    if cache_key in CACHE and now - CACHE[cache_key]['time'] < CACHE_TIME:
        return CACHE[cache_key]['data']
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd,cny"
    try:
        resp = requests.get(url, timeout=10).json()
        if coin_id in resp:
            CACHE[cache_key] = {'data': resp, 'time': now}
            return resp
    except Exception as e:
        print(f"查询 {coin_id} 价格失败:", e)
    return None

def format_change(value):
    if value is None:
        return "N/A"
    arrow = "📈" if value >= 0 else "📉"
    sign = "+" if value >= 0 else ""
    return f"{arrow} {sign}{value:.2f}%"

def reply_crypto_price(chat_id, symbol):
    coin_id = COIN_MAP.get(symbol, symbol)
    data = get_crypto_market_data(coin_id)
    if not data:
        send_message(chat_id, "未找到该币种，请检查输入。")
        return
    simple_data = get_crypto_simple_price(coin_id)
    usd_price = None
    cny_price = None
    if simple_data and coin_id in simple_data:
        usd_price = simple_data[coin_id].get('usd')
        cny_price = simple_data[coin_id].get('cny')
    change_24h = data.get('price_change_percentage_24h')
    change_7d = data.get('price_change_percentage_7d_in_currency')
    msg = f"📊 {symbol.upper()} 行情\n"
    msg += "━━━━━━━━━━━━\n"
    if usd_price is not None:
        msg += f"🇺🇸 价格：${usd_price:,.2f}\n"
    if cny_price is not None:
        msg += f"🇨🇳 价格：¥{cny_price:,.2f}\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"📅 24h涨跌：{format_change(change_24h)}\n"
    msg += f"📆 7d涨跌：{format_change(change_7d)}"
    send_message(chat_id, msg)

def reply_fiat_rate(chat_id, base, quote):
    try:
        url = f"https://api.frankfurter.app/latest?from={base}&to={quote}"
        resp = requests.get(url, timeout=10).json()
        if "rates" in resp and quote in resp["rates"]:
            val = resp["rates"][quote]
            send_message(chat_id, f"💱 1 {base} = {val:.4f} {quote}")
        else:
            send_message(chat_id, "不支持该货币对。")
    except Exception as e:
        send_message(chat_id, f"查询失败：{e}")

def handle_message(chat_id, text):
    raw_text = text.strip().lower()
    if raw_text in COIN_MAP:
        reply_crypto_price(chat_id, raw_text)
        return
    if raw_text in FIAT_MAP:
        base = FIAT_MAP[raw_text]
        quote = "USD" if base == "CNY" else "CNY"
        reply_fiat_rate(chat_id, base, quote)
        return
    if raw_text in ("/start", "/help"):
        send_message(chat_id, "你好！我是货币价格机器人。\n\n快捷指令（直接发送币种即可）：\nbtc / 比特币\neth / 以太坊\nusd / 美元\n\n完整命令：\n/price btc\n/rate usd cny\n/convert 100 usd cny\n/convert 1 btc usd")
    elif raw_text.startswith("/price"):
        args = raw_text.split()
        if len(args) < 2:
            send_message(chat_id, "用法：/price btc")
            return
        reply_crypto_price(chat_id, args[1])
    elif raw_text.startswith("/rate"):
        args = raw_text.split()
        if len(args) < 3:
            send_message(chat_id, "用法：/rate usd cny")
            return
        base = args[1].upper()
        quote = args[2].upper()
        reply_fiat_rate(chat_id, base, quote)
    elif raw_text.startswith("/convert"):
        args = raw_text.split()
        if len(args) < 4:
            send_message(chat_id, "用法：/convert 100 usd cny 或 /convert 1 btc usd")
            return
        try:
            amount = float(args[1])
            base = args[2].lower()
            quote = args[3].lower()
        except ValueError:
            send_message(chat_id, "金额必须是数字。")
            return
        if base in COIN_MAP:
            coin_id = COIN_MAP[base]
            simple_data = get_crypto_simple_price(coin_id)
            if simple_data and coin_id in simple_data:
                if quote == "usd":
                    rate = simple_data[coin_id].get("usd")
                    if rate:
                        result = amount * rate
                        send_message(chat_id, f"💰 {amount} {base.upper()} = ${result:,.2f} USD")
                        return
                elif quote == "cny":
                    rate = simple_data[coin_id].get("cny")
                    if rate:
                        result = amount * rate
                        send_message(chat_id, f"💰 {amount} {base.upper()} = ¥{result:,.2f} CNY")
                        return
                else:
                    send_message(chat_id, "暂不支持该加密货币兑换此货币。")
                    return
            send_message(chat_id, "查询加密货币价格失败。")
            return
        base_upper = args[2].upper()
        quote_upper = args[3].upper()
        try:
            url = f"https://api.frankfurter.app/latest?from={base_upper}&to={quote_upper}"
            resp = requests.get(url, timeout=10).json()
            if "rates" in resp and quote_upper in resp["rates"]:
                result = amount * resp["rates"][quote_upper]
                send_message(chat_id, f"💱 {amount:,.2f} {base_upper} = {result:,.2f} {quote_upper}")
            else:
                send_message(chat_id, "不支持该法币对。")
        except Exception as e:
            send_message(chat_id, f"查询失败：{e}")
    else:
        send_message(chat_id, "输入 /help 查看用法，或直接输入币种名称（如 btc、美元）。")

def main():
    print("Bot 已启动...")
    offset = None
    while True:
        updates = get_updates(offset)
        if "result" in updates:
            for update in updates["result"]:
                offset = update["update_id"] + 1
                message = update.get("message")
                if not message:
                    continue
                chat_id = message["chat"]["id"]
                text = message.get("text", "")
                if text:
                    handle_message(chat_id, text)
        time.sleep(1)

if __name__ == "__main__":
    main()