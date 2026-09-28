import os
import requests
import time

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# CoinCap 的币种映射
COIN_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "DOGE": "dogecoin",
    "BNB": "binance-coin",
    "XRP": "xrp",
    "ADA": "cardano",
    "DOT": "polkadot",
    "LTC": "litecoin",
    "SHIB": "shiba-inu",
    "AVAX": "avalanche",
    "LINK": "chainlink"
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

def get_crypto_data(symbol):
    coin_id = COIN_MAP.get(symbol, symbol.lower())
    
    # 1. 获取当前价格和24小时涨跌幅
    url_now = f"https://api.coincap.io/v2/assets/{coin_id}"
    try:
        resp = requests.get(url_now, timeout=10).json()
        if "data" not in resp:
            return None, f"CoinCap 找不到 {coin_id}"
        
        data = resp["data"]
        price_usd = float(data["priceUsd"])
        change_24h = float(data["changePercent24Hr"])
    except Exception as e:
        print(f"CoinCap 请求异常: {e}")
        return None, "网络请求异常"

    # 2. 获取7天涨跌幅
    change_7d = None
    url_history = f"https://api.coincap.io/v2/assets/{coin_id}/history?interval=d1&limit=8"
    try:
        hist_resp = requests.get(url_history, timeout=10).json()
        if "data" in hist_resp and len(hist_resp["data"]) >= 8:
            price_7d_ago = float(hist_resp["data"][0]["priceUsd"])
            change_7d = ((price_usd - price_7d_ago) / price_7d_ago) * 100
    except Exception as e:
        print(f"CoinCap 历史数据异常: {e}")

    # 3. 获取美元兑人民币汇率
    price_cny = None
    try:
        fx_resp = requests.get("https://api.frankfurter.app/latest?from=USD&to=CNY", timeout=5).json()
        if "rates" in fx_resp and "CNY" in fx_resp["rates"]:
            usd_cny_rate = fx_resp["rates"]["CNY"]
            price_cny = price_usd * usd_cny_rate
    except Exception as e:
        print(f"汇率请求异常: {e}")

    return {
        "price_usd": price_usd,
        "price_cny": price_cny,
        "change_24h": change_24h,
        "change_7d": change_7d
    }, None

def reply_crypto(chat_id, symbol):
    data, err = get_crypto_data(symbol)
    
    if err:
        # 严格遵照你的要求：查询失败时，默默记录到 Railway 日志，绝不发送任何 Telegram 消息
        print(f"查询 {symbol} 失败: {err}")
        return

    # 处理极小价格（如 SHIB），动态调整小数位数
    price_usd = data['price_usd']
    price_cny = data['price_cny']
    
    if price_usd < 0.01:
        usd_str = f"${price_usd:,.8f}"
        cny_str = f"¥{price_cny:,.8f}" if price_cny else "¥ --"
    else:
        usd_str = f"${price_usd:,.4f}"
        cny_str = f"¥{price_cny:,.4f}" if price_cny else "¥ --"

    msg = f"📊 {symbol} 行情\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"🇺🇸 价格：{usd_str}\n"
    msg += f"🇨🇳 价格：{cny_str}\n"
    msg += "━━━━━━━━━━━━\n"
    
    c24 = data['change_24h']
    if c24 is not None:
        arrow_24 = "📈" if c24 >= 0 else "📉"
        msg += f"{arrow_24} 24h涨跌：{c24:+.2f}%\n"
        
    c7 = data['change_7d']
    if c7 is not None:
        arrow_7 = "📈" if c7 >= 0 else "📉"
        msg += f"{arrow_7} 7d涨跌：{c7:+.2f}%"
        
    send_message(chat_id, msg)

def handle_message(chat_id, text):
    raw_text = text.strip()
    
    # 严格按照要求：只处理 "币种名称+." 格式，例如 btc. / ETH.
    # 不区分大小写
    if raw_text.endswith("."):
        symbol = raw_text[:-1].upper()
        if symbol.isalpha() and 2 <= len(symbol) <= 10:
            reply_crypto(chat_id, symbol)
            return
    
    # 其他所有消息（包括 /start, /help, 聊天文字等），直接静默忽略，不回复任何内容
    return

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
