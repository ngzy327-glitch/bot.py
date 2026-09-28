import os
import requests
import time

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# CoinGecko 的币种映射
COIN_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "DOGE": "dogecoin",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOT": "polkadot",
    "LTC": "litecoin"
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
    
    # 1. 获取美元兑人民币汇率
    cny_rate = 7.2
    try:
        fx_resp = requests.get("https://api.frankfurter.app/latest?from=USD&to=CNY", timeout=5).json()
        if "rates" in fx_resp and "CNY" in fx_resp["rates"]:
            cny_rate = fx_resp["rates"]["CNY"]
    except:
        pass

    # 2. 获取 CoinGecko 行情数据（价格+涨跌幅）
    url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={coin_id}&price_change_percentage=24h,7d"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None, f"API返回错误，状态码：{resp.status_code}"
            
        data = resp.json()
        if not isinstance(data, list) or len(data) == 0:
            return None, "API返回数据为空"
            
        item = data[0]
        if "current_price" not in item:
            return None, "找不到该币种"

        price_usd = item["current_price"]
        price_cny = price_usd * cny_rate
        
        change_24h = item.get("price_change_percentage_24h")
        change_7d = item.get("price_change_percentage_7d_in_currency")
        
        return {
            "price_usd": price_usd,
            "price_cny": price_cny,
            "change_24h": change_24h,
            "change_7d": change_7d
        }, None
        
    except Exception as e:
        print(f"CoinGecko 请求异常: {e}")
        return None, f"网络请求异常: {e}"

def reply_crypto(chat_id, symbol):
    data, err = get_crypto_data(symbol)
    
    if err:
        # 严格遵照你的要求：查询失败时，默默记录到 Railway 日志，绝不发送任何 Telegram 消息
        print(f"查询 {symbol} 失败: {err}")
        return

    price_usd = data['price_usd']
    price_cny = data['price_cny']
    c24 = data['change_24h']
    c7 = data['change_7d']

    # 处理极小价格（如 SHIB），动态调整小数位数
    if price_usd < 0.01:
        usd_str = f"${price_usd:,.8f}"
        cny_str = f"¥{price_cny:,.8f}"
    else:
        usd_str = f"${price_usd:,.4f}"
        cny_str = f"¥{price_cny:,.4f}"

    msg = f"📊 {symbol} 行情\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"🇺🇸 价格：{usd_str}\n"
    msg += f"🇨🇳 价格：{cny_str}\n"
    msg += "━━━━━━━━━━━━\n"
    
    if c24 is not None:
        arrow_24 = "📈" if c24 >= 0 else "📉"
        msg += f"{arrow_24} 24h涨跌：{c24:+.2f}%\n"
        
    if c7 is not None:
        arrow_7 = "📈" if c7 >= 0 else "📉"
        msg += f"{arrow_7} 7d涨跌：{c7:+.2f}%"
    else:
        msg += "7d涨跌：获取失败"
        
    send_message(chat_id, msg)

def handle_message(chat_id, text):
    raw_text = text.strip()
    
    # 严格依照你的要求：仅处理 "币种名称+." 格式，不区分大小写
    if raw_text.endswith("."):
        symbol = raw_text[:-1].upper()
        if symbol.isalpha() and 2 <= len(symbol) <= 10:
            reply_crypto(chat_id, symbol)
            return
    
    # 其他所有消息一律沉默，不回复任何教程或提示
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
    
