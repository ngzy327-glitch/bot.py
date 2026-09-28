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

def get_crypto_data(user_input):
    symbol = user_input.upper()
    if not symbol.endswith("USDT"):
        symbol = symbol + "USDT"

    url_24h = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
    try:
        resp = requests.get(url_24h, timeout=10)
        if resp.status_code == 400:
            return None, "找不到该交易对"
        
        data = resp.json()
        if "lastPrice" not in data:
            return None, "数据格式错误"

        price_usd = float(data["lastPrice"])
        change_24h = float(data["priceChangePercent"])
        
        url_kline = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=8"
        kline_resp = requests.get(url_kline, timeout=10).json()
        change_7d = None
        if isinstance(kline_resp, list) and len(kline_resp) >= 8:
            price_7d_ago = float(kline_resp[0][4])
            change_7d = ((price_usd - price_7d_ago) / price_7d_ago) * 100

        usd_cny_rate = 7.2
        try:
            fx_resp = requests.get("https://api.frankfurter.app/latest?from=USD&to=CNY", timeout=5).json()
            if "rates" in fx_resp and "CNY" in fx_resp["rates"]:
                usd_cny_rate = fx_resp["rates"]["CNY"]
        except:
            pass

        price_cny = price_usd * usd_cny_rate

        return {
            "price_usd": price_usd,
            "price_cny": price_cny,
            "change_24h": change_24h,
            "change_7d": change_7d
        }, None

    except Exception as e:
        print(f"请求币安API异常: {e}")
        return None, "网络请求异常"

def reply_crypto(chat_id, user_input):
    data, err = get_crypto_data(user_input)
    if err:
        # 查询失败时，默默记录到日志，绝对不发给用户，防止消息轰炸
        print(f"查询 {user_input} 失败: {err}")
        return

    msg = f"📊 {user_input.upper()} 行情\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"🇺🇸 价格：${data['price_usd']:,.2f}\n"
    msg += f"🇨🇳 价格：¥{data['price_cny']:,.2f}\n"
    msg += "━━━━━━━━━━━━\n"
    
    arrow_24 = "📈" if data['change_24h'] >= 0 else "📉"
    msg += f"{arrow_24} 24h涨跌：{data['change_24h']:+.2f}%\n"
    
    if data['change_7d'] is not None:
        arrow_7 = "📈" if data['change_7d'] >= 0 else "📉"
        msg += f"{arrow_7} 7d涨跌：{data['change_7d']:+.2f}%"
    else:
        msg += "7d涨跌：获取失败"
        
    send_message(chat_id, msg)

def handle_message(chat_id, text):
    raw_text = text.strip().upper()
    
    # 1. 如果是 /price 命令，提取币种
    if raw_text.startswith("/PRICE"):
        args = raw_text.split()
        if len(args) < 2:
            return # 静默，不回复用法教程
        reply_crypto(chat_id, args[1])
    
    # 2. 如果是纯字母（长度2-10），认为可能是币种代码（如 BTC, ETH, SOL）
    # 满足条件才去查询，查不到会默默失败，不会发送任何错误消息
    elif raw_text.isalpha() and 2 <= len(raw_text) <= 10:
        reply_crypto(chat_id, raw_text)
    
    # 3. 其他任何输入（包括 /start, /help, 普通聊天、中文），直接忽略，一言不发
    else:
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
