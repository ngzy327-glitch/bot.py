import os
import requests
import time

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
CACHE = {}
CACHE_TIME = 60

# 加密货币映射，这里包含主流币种
COIN_MAP = {
    "btc": "BTCUSDT", "比特币": "BTCUSDT",
    "eth": "ETHUSDT", "以太坊": "ETHUSDT",
    "sol": "SOLUSDT", "solana": "SOLUSDT",
    "doge": "DOGEUSDT", "狗狗币": "DOGEUSDT",
    "bnb": "BNBUSDT", "币安币": "BNBUSDT",
    "xrp": "XRPUSDT", "ripple": "XRPUSDT",
    "ada": "ADAUSDT", "cardano": "ADAUSDT",
    "dot": "DOTUSDT", "polkadot": "DOTUSDT",
    "ltc": "LTCUSDT", "litecoin": "LTCUSDT",
    "usdt": "USDCUSDT", "usdc": "USDCUSDT"
}

# 法币映射
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

def get_usd_cny_rate():
    try:
        url = "https://api.frankfurter.app/latest?from=USD&to=CNY"
        resp = requests.get(url, timeout=10).json()
        if "rates" in resp and "CNY" in resp["rates"]:
            return resp["rates"]["CNY"]
    except Exception as e:
        print("查询汇率失败:", e)
    return 7.2 # 默认备用汇率

def get_crypto_data(symbol):
    now = time.time()
    if symbol in CACHE and now - CACHE[symbol]['time'] < CACHE_TIME:
        return CACHE[symbol]['data']
        
    try:
        # 1. 获取 24小时 行情
        url_24h = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
        data_24h = requests.get(url_24h, timeout=10).json()
        
        # 2. 获取 K线 算 7日涨跌幅 (8天数据)
        url_kline = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=8"
        data_kline = requests.get(url_kline, timeout=10).json()
        
        if not data_24h or "lastPrice" not in data_24h:
            return None
            
        price = float(data_24h["lastPrice"])
        change_24h = float(data_24h["priceChangePercent"])
        
        change_7d = None
        if isinstance(data_kline, list) and len(data_kline) >= 8:
            price_7d_ago = float(data_kline[0][4])
            change_7d = ((price - price_7d_ago) / price_7d_ago) * 100
            
        result = {
            "usd": price,
            "change_24h": change_24h,
            "change_7d": change_7d
        }
        
        CACHE[symbol] = {'data': result, 'time': now}
        return result
        
    except Exception as e:
        print(f"查询 {symbol} 行情失败: {e}")
        return None

def reply_crypto_price(chat_id, symbol):
    pair = COIN_MAP.get(symbol, symbol)
    data = get_crypto_data(pair)
    
    if not data:
        send_message(chat_id, "未找到该币种，请检查输入。")
        return

    usd_price = data['usd']
    # 计算人民币价格
    usd_cny = get_usd_cny_rate()
    cny_price = usd_price * usd_cny

    change_24h = data['change_24h']
    change_7d = data['change_7d']

    msg = f"📊 {symbol.upper()} 行情\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"🇺🇸 价格：${usd_price:,.2f}\n"
    msg += f"🇨🇳 价格：¥{cny_price:,.2f}\n"
    msg += "━━━━━━━━━━━━\n"
    
    if change_24h is not None:
        arrow = "📈" if change_24h >= 0 else "📉"
        msg += f"{arrow} 24h涨跌：{change_24h:+.2f}%\n"
        
    if change_7d is not None:
        arrow = "📈" if change_7d >= 0 else "📉"
        msg += f"{arrow} 7d涨跌：{change_7d:+.2f}%"
        
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
        send_message(chat_id, "你好！我是货币价格机器人。\n\n快捷指令（直接发送币种即可）：\nbtc / 比特币\neth / 以太坊\nusd / 美元\n\n完整命令：\n/price btc\n/rate usd cny\n/convert 100 usd cny")
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
            pair = COIN_MAP[base]
            data = get_crypto_data(pair)
            if data:
                usd_cny = get_usd_cny_rate()
                if quote == "usd":
                    result = amount * data['usd']
                    send_message(chat_id, f"💰 {amount} {base.upper()} = ${result:,.2f} USD")
                    return
                elif quote == "cny":
                    result = amount * data['usd'] * usd_cny
                    send_message(chat_id, f"💰 {amount} {base.upper()} = ¥{result:,.2f} CNY")
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
