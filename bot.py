import os
import requests
import time

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

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
    # 使用 OKX 交易所公开接口，无需 API Key，容错率高
    okx_symbol = f"{symbol}-USDT"
    
    # 1. 获取最新价格和 24h 开盘价
    url_ticker = f"https://www.okx.com/api/v5/market/ticker?instId={okx_symbol}"
    try:
        resp = requests.get(url_ticker, timeout=10).json()
        if resp.get("code") != "0" or not resp.get("data"):
            return None, f"OKX 找不到交易对 {okx_symbol}"
            
        item = resp["data"][0]
        last_price = float(item["last"])
        open_24h = float(item["open24h"])
        
        if open_24h == 0:
            change_24h = 0.0
        else:
            change_24h = ((last_price - open_24h) / open_24h) * 100
            
    except Exception as e:
        print(f"OKX 行情请求异常: {e}")
        return None, "网络请求异常"

    # 2. 获取 8 天 K 线计算 7d 涨跌幅
    change_7d = None
    url_kline = f"https://www.okx.com/api/v5/market/candles?instId={okx_symbol}&bar=1D&limit=8"
    try:
        kline_resp = requests.get(url_kline, timeout=10).json()
        if kline_resp.get("code") == "0" and len(kline_resp.get("data", [])) >= 8:
            # OKX K线格式：[时间, 开盘, 最高, 最低, 收盘, 成交量, ...]
            price_7d_ago = float(kline_resp["data"][0][4])
            change_7d = ((last_price - price_7d_ago) / price_7d_ago) * 100
    except Exception as e:
        print(f"OKX K线请求异常: {e}")

    # 3. 获取美元兑人民币汇率
    price_cny = None
    try:
        fx_resp = requests.get("https://api.frankfurter.app/latest?from=USD&to=CNY", timeout=5).json()
        if "rates" in fx_resp and "CNY" in fx_resp["rates"]:
            usd_cny_rate = fx_resp["rates"]["CNY"]
            price_cny = last_price * usd_cny_rate
    except Exception as e:
        print(f"汇率请求异常: {e}")

    return {
        "price_usd": last_price,
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

    price_usd = data['price_usd']
    price_cny = data['price_cny']
    c24 = data['change_24h']
    c7 = data['change_7d']

    # 处理极小价格（如 SHIB），动态调整小数位数
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
