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
        
        # 检查是否成功返回数据
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
            # 记录真实的错误信息到日志，但不发给用户
            error_msg = resp.get("Message", "找不到该币种或数据格式错误")
            return None, error_msg

    except Exception as e:
        print(f"请求异常: {e}")
        return None, "网络请求异常"

def reply_crypto(chat_id, user_input):
    # 只提取字母，并转为大写，防止用户输入 "btc " 或 "BTC."
    symbol = re.sub(r'[^A-Za-z]', '', user_input.upper())
    if not symbol:
        return

    data, err = get_crypto_data(symbol)
    
    if err:
        # 严格遵照你的要求：查询失败时，默默记录到 Railway 日志，绝不发送任何 Telegram 消息
        print(f"查询 {symbol} 失败: {err}")
        return

    msg = f"📊 {symbol} 行情\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"🇺🇸 价格：${data['price_usd']:,.4f}\n"
    msg += f"🇨🇳 价格：¥{data['price_cny']:,.4f}\n"
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
    raw_text = text.strip().upper()
    
    # 1. 如果是 /price 命令
    if raw_text.startswith("/PRICE"):
        args = raw_text.split()
        if len(args) >= 2:
            reply_crypto(chat_id, args[1])
        return

    # 2. 如果用户直接输入币种，提取字母后的长度在 2 到 10 之间，才尝试查询
    clean_symbol = re.sub(r'[^A-Z]', '', raw_text)
    if 2 <= len(clean_symbol) <= 10:
        reply_crypto(chat_id, clean_symbol)
        return
        
    # 3. 其他所有情况（包括 /start, /help, 中文聊天等），直接静默忽略，不回复任何内容
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
