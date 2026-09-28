import os
import re
import time
import json
import threading
import requests
import hmac
import hashlib
from urllib.parse import urlencode

BOT_TOKEN = os.getenv("BOT_TOKEN")
GATE_API_KEY = os.getenv("GATE_API_KEY")
GATE_API_SECRET = os.getenv("GATE_API_SECRET")
GATE_BASE_URL = os.getenv("GATE_BASE_URL", "https://api-testnet.gateapi.io/api/v4")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

LISTENERS = []
LISTENER_LOCK = threading.Lock()

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

def gen_sign(method, url, query_string="", body_string=""):
    t = time.time()
    m = hashlib.sha512()
    m.update(body_string.encode("utf-8"))
    body_hash = m.hexdigest()
    timestamp = str(int(t))
    sign_string = f"{method}\n{url}\n{query_string}\n{body_hash}\n{timestamp}"
    sign = hmac.new(
        GATE_API_SECRET.encode("utf-8"),
        sign_string.encode("utf-8"),
        hashlib.sha512
    ).hexdigest()
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "KEY": GATE_API_KEY,
        "Timestamp": timestamp,
        "SIGN": sign,
    }
    return headers

def gate_request(method, endpoint, params=None, body=None):
    url = f"{GATE_BASE_URL}{endpoint}"
    query_string = urlencode(params) if params else ""
    body_string = body if body else ""
    headers = gen_sign(method, endpoint, query_string, body_string)
    try:
        if method == "GET":
            resp = requests.get(f"{url}?{query_string}", headers=headers, timeout=10)
        elif method == "POST":
            resp = requests.post(url, headers=headers, data=body_string, timeout=10)
        else:
            return None
        return resp.json()
    except Exception as e:
        print(f"Gate.io 请求异常: {e}")
        return None

def get_current_price(symbol):
    try:
        resp = requests.get(f"{GATE_BASE_URL}/futures/usdt/tickers?contract={symbol}", timeout=5).json()
        if isinstance(resp, list) and len(resp) > 0:
            return float(resp[0]["last"])
    except:
        pass
    return None

def get_balance_info(chat_id):
    res = gate_request("GET", "/futures/usdt/accounts")
    if not isinstance(res, dict) or "total" not in res:
        send_message(chat_id, "❌ 获取余额失败，请检查 API 权限或网络。")
        return

    total = float(res.get("total", 0))
    available = float(res.get("available", 0))

    msg = f"💰 合约账户余额\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"总金额：{total:,.2f} USDT\n"
    msg += f"可用余额：{available:,.2f} USDT"
    send_message(chat_id, msg)

def get_position_info(chat_id):
    res = gate_request("GET", "/futures/usdt/positions")
    if not isinstance(res, list):
        send_message(chat_id, "❌ 获取持仓失败，请检查 API 权限或网络。")
        return

    active = [p for p in res if int(p.get("size", 0)) != 0]
    if not active:
        send_message(chat_id, "📭 当前无持仓。")
        return

    for pos in active:
        contract = pos["contract"]
        size = int(pos["size"])
        entry_price = float(pos.get("entry_price", 0))
        mark_price = float(pos.get("mark_price", 0))
        leverage = pos.get("leverage", "0")
        margin = float(pos.get("margin", 0))
        unrealised_pnl = float(pos.get("unrealised_pnl", 0))
        liq_price = float(pos.get("liq_price", 0))
        
        roe = (unrealised_pnl / margin) * 100 if margin > 0 else 0.0
        direction = "多 🟢" if size > 0 else "空 🔴"

        msg = f"📊 {contract} 仓位情况\n"
        msg += "━━━━━━━━━━━━\n"
        msg += f"方向：{direction}\n"
        msg += f"持仓张数：{abs(size)}\n"
        msg += f"开仓价：${entry_price:,.4f}\n"
        msg += f"标记价：${mark_price:,.4f}\n"
        msg += f"爆仓价：${liq_price:,.4f}\n"
        msg += "━━━━━━━━━━━━\n"
        msg += f"保证金：{margin:,.2f} USDT\n"
        msg += f"杠杆：{leverage}x\n"
        msg += f"收益率：{roe:+.2f}%\n"
        msg += f"未实现盈亏：{unrealised_pnl:+.2f} USDT"
        send_message(chat_id, msg)

def execute_trade(chat_id, symbol, side, dir_name, leverage, margin_usdt):
    # 1. 设置杠杆
    lev_body = json.dumps({"leverage": str(leverage)})
    lev_res = gate_request("POST", f"/futures/usdt/positions/{symbol}/leverage", body=lev_body)
    if isinstance(lev_res, dict) and "leverage" not in lev_res:
        send_message(chat_id, f"❌ 设置杠杆失败：{lev_res.get('message', '未知错误')}")
        return

    # 2. 获取当前价格和合约面值
    price = get_current_price(symbol)
    if not price:
        send_message(chat_id, f"❌ 找不到交易对 {symbol}，无法下单。")
        return

    contract_info = gate_request("GET", f"/futures/usdt/contracts/{symbol}")
    if not isinstance(contract_info, dict) or "quanto_multiplier" not in contract_info:
        send_message(chat_id, "❌ 获取合约面值失败，无法计算下单张数。")
        return
    
    multiplier = float(contract_info["quanto_multiplier"])
    
    # 3. 计算下单张数：(保证金 * 杠杆) / (价格 * 面值)
    size = int((margin_usdt * leverage) / (price * multiplier))
    if size <= 0:
        send_message(chat_id, f"❌ 保证金过小，计算出的下单张数为 0。")
        return

    # 4. 市价开仓
    order_body = {
        "contract": symbol,
        "size": size,
        "price": "0",     # 市价单填 0
        "tif": "ioc",     # 立即成交否则取消
        "side": side      # buy / sell
    }
    order_res = gate_request("POST", "/futures/usdt/orders", body=json.dumps(order_body))

    if order_res and "id" in order_res:
        msg = f"✅ 开仓成功！\n"
        msg += f"币种：{symbol}\n"
        msg += f"方向：{dir_name}\n"
        msg += f"杠杆：{leverage}x\n"
        msg += f"保证金：{margin_usdt:,.2f} USDT\n"
        msg += f"张数：{size}"
        send_message(chat_id, msg)
    else:
        error_msg = order_res.get("message", "未知错误") if order_res else "请求失败"
        print(f"开仓失败: {order_res}")
        send_message(chat_id, f"❌ 开仓失败：{error_msg}")

def price_monitor_worker():
    print("价格监听线程已启动...")
    while True:
        try:
            with LISTENER_LOCK:
                current_listeners = list(LISTENERS)
            for listener in current_listeners:
                symbol = listener["symbol"]
                target_price = listener["target_price"]
                chat_id = listener["chat_id"]
                current_price = get_current_price(symbol)
                if current_price is None:
                    continue
                triggered = False
                if target_price > current_price:
                    if current_price >= target_price:
                        triggered = True
                else:
                    if current_price <= target_price:
                        triggered = True
                if triggered:
                    msg = f"🚨 价格提醒！\n"
                    msg += f"交易对：{symbol}\n"
                    msg += f"当前价：${current_price:,.4f}\n"
                    msg += f"目标价：${target_price:,.4f}"
                    send_message(chat_id, msg)
                    with LISTENER_LOCK:
                        if listener in LISTENERS:
                            LISTENERS.remove(listener)
        except Exception as e:
            print(f"监听线程异常: {e}")
        time.sleep(30)

def handle_message(chat_id, text):
    raw_text = text.strip()

    if raw_text == "myye":
        get_balance_info(chat_id)
        return

    if raw_text == "仓位情况":
        get_position_info(chat_id)
        return

    listen_match = re.match(r'^监听\s*([a-zA-Z]+)\s*([0-9.]+)$', raw_text)
    if listen_match:
        symbol_str = listen_match.group(1).upper()
        target_price_str = listen_match.group(2)
        if not symbol_str.endswith("_USDT"):
            symbol_str += "_USDT"
        try:
            target_price = float(target_price_str)
        except ValueError:
            return
        if target_price <= 0:
            send_message(chat_id, "❌ 监听价格必须大于 0。")
            return
        with LISTENER_LOCK:
            for listener in LISTENERS:
                if listener["symbol"] == symbol_str and listener["target_price"] == target_price:
                    send_message(chat_id, "⚠️ 该监听已存在。")
                    return
            LISTENERS.append({
                "symbol": symbol_str,
                "target_price": target_price,
                "chat_id": chat_id
            })
        send_message(chat_id, f"✅ 已开启监听：{symbol_str} 达到 ${target_price:,.4f} 时通知你。")
        return

    normalized_text = raw_text.replace("，", ",").replace(" ", ",")
    parts = [p for p in normalized_text.split(",") if p]

    if len(parts) == 4:
        symbol = parts[0].upper()
        if not symbol.endswith("_USDT"):
            symbol += "_USDT"
        lev_str = parts[1].lower().replace("x", "")
        if not lev_str.isdigit():
            return
        leverage = int(lev_str)
        if leverage <= 0 or leverage > 125:
            send_message(chat_id, "❌ 杠杆范围必须在 1-125 之间。")
            return
        direction = parts[2].lower()
        if direction in ["多", "long", "buy"]:
            side = "buy"
            dir_name = "做多"
        elif direction in ["空", "short", "sell"]:
            side = "sell"
            dir_name = "做空"
        else:
            return
        try:
            margin_usdt = float(parts[3])
        except ValueError:
            return
        if margin_usdt <= 0:
            send_message(chat_id, "❌ 保证金必须大于 0。")
            return
        execute_trade(chat_id, symbol, side, dir_name, leverage, margin_usdt)
        return

    return

def main():
    if not ALLOWED_USER_ID:
        print("警告：未设置 ALLOWED_USER_ID，机器人将对所有人开放！")
    else:
        print(f"权限控制已开启，只允许 User ID: {ALLOWED_USER_ID} 操作。")

    monitor_thread = threading.Thread(target=price_monitor_worker, daemon=True)
    monitor_thread.start()

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
                if ALLOWED_USER_ID:
                    from_user = message.get("from", {})
                    user_id = str(from_user.get("id", ""))
                    if user_id != ALLOWED_USER_ID:
                        print(f"未授权用户尝试操作: {user_id}")
                        continue
                chat_id = message["chat"]["id"]
                text = message.get("text", "")
                if text:
                    handle_message(chat_id, text)
        time.sleep(1)

if __name__ == "__main__":
    main()
