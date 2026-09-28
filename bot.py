import os
import requests
import time
import re

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
    # 使用 CryptoCompare 接口，直接获取美元、人民币价格及涨跌幅
    url = f"https://min-api.cryptocompare.com/data/pricemultifull?fsyms={symbol}&tsyms=USD,CNY"
    try:
        resp = requests.get(url, timeout=10).json()
        
        if "RAW" in resp and symbol in resp["RAW"]:
            usd_data = resp["RAW"][symbol]["USD"]
            cny_data = resp["RAW"][symbol]["CNY"]
            
            return {
                "price_usd": usd_data["PRICE"],
                "price_cny": cny_data["PRICE"],
                "change_24h": usd_data.get("CHANGEPCT24HOUR"),
                "change_7d": usd_data.get("CHANGEPCT7DAYS")
            }, None
        else:
            error_msg = resp.get("Message", "找不到该币种")
            return None, error_msg

    except Exception as e:
        print(f"请求异常: {e}")
        return None, "网络请求异常"

def reply_crypto(chat_id, symbol):
    data, err = get_crypto_data(symbol)
    
    if err:
        # 严格遵守你的要求：查询失败默默记录日志，绝不发送任何 Telegram 消息
        print(f"查询 {symbol} 失败: {err}")
        return

    # 处理极小价格（如 SHIB），动态调整小数位数
    price_usd = data['price_usd']
    price_cny = data['price_cny']
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
        # 去掉点号后，必须是纯英文字母，且长度合理（例如 2 到 10 位）
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
