import os
import re
import time
import threading
import requests
import hmac
import hashlib
from urllib.parse import urlencode

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
# 币安合约测试网，如果是实盘请改成 https://fapi.binance.com
BINANCE_BASE_URL = "https://testnet.binancefuture.com"

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

def get_current_price(symbol):
    try:
        resp = requests.get(f"{BINANCE_BASE_URL}/fapi/v1/ticker/price?symbol={symbol}", timeout=5).json()
        if "price" in resp:
            return float(resp["price"])
    except:
        pass
    return None

def binance_request(method, endpoint, params=None):
    if params is None:
        params = {}
    params["timestamp"] = int(time.time() * 1000)
    query_string = urlencode(params)
    signature = hmac.new(
        API_SECRET.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    params["signature"] = signature
    url = f"{BINANCE_BASE_URL}{endpoint}"
    headers = {"X-MBX-APIKEY": API_KEY}
    try:
        if method == "GET":
            resp = requests.get(url, params=params, headers=headers, timeout=10)
        else:
            resp = requests.post(url, params=params, headers=headers, timeout=10)
        return resp.json()
    except Exception as e:
        print(f"币安请求异常: {e}")
        return None

def set_leverage(symbol, leverage):
    return binance_request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage})

def place_order(symbol, side, quantity):
    return binance_request("POST", "/fapi/v1/order", {"symbol": symbol, "side": side, "type": "MARKET", "quantity": quantity})

def get_balance_info(chat_id):
    """查询合约账户余额"""
    res = binance_request("GET", "/fapi/v2/balance")
    if not isinstance(res, list):
        send_message(chat_id, "❌ 获取余额失败，请检查 API 权限或网络。")
        return
    
    usdt_info = None
    for b in res:
        if b.get("asset") == "USDT":
            usdt_info = b
            break
            
    if not usdt_info:
        send_message(chat_id, "❌ 未找到 USDT 资产信息。")
        return

    total_balance = float(usdt_info.get("balance", 0))
    available_balance = float(usdt_info.get("availableBalance", 0))

    msg = f"💰 账户余额\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"总金额：{total_balance:,.2f} USDT\n"
    msg += f"可用余额：{available_balance:,.2f} USDT"
    send_message(chat_id, msg)

def get_position_info(chat_id):
    positions = binance_request("GET", "/fapi/v2/positionRisk")
    if not positions or not isinstance(positions, list):
        send_message(chat_id, "❌ 获取仓位失败，请检查 API 权限或网络。")
        return

    active_positions = [p for p in positions if float(p.get("positionAmt", 0)) != 0]
    if not active_positions:
        send_message(chat_id, "📭 当前无持仓。")
        return

    for pos in active_positions:
        symbol = pos["symbol"]
        amt = float(pos["positionAmt"])
        entry_price = float(pos["entryPrice"])
        mark_price = float(pos["markPrice"])
        liq_price = float(pos["liquidationPrice"])
        leverage = pos["leverage"]
        unrealized_pnl = float(pos["unRealizedProfit"])
        initial_margin = float(pos.get("initialMargin", 0))
        isolated_margin = float(pos.get("isolatedMargin", 0))
        margin = isolated_margin if isolated_margin > 0 else initial_margin
        
        roe = (unrealized_pnl / margin) * 100 if margin > 0 else 0.0
        direction = "多 🟢" if amt > 0 else "空 🔴"
        
        tp_price = "未设置"
        sl_price = "未设置"
        orders = binance_request("GET", "/fapi/v1/openOrders", {"symbol": symbol})
        if isinstance(orders, list):
            for o in orders:
                if "TAKE_PROFIT" in o.get("type", ""):
                    tp_price = o.get("stopPrice", "未设置")
                if "STOP" in o.get("type", ""):
                    sl_price = o.get("stopPrice", "未设置")

        msg = f"📊 {symbol} 仓位情况\n"
        msg += "━━━━━━━━━━━━\n"
        msg += f"方向：{direction}\n"
        msg += f"持仓量：{abs(amt)}\n"
        msg += f"开仓价：${entry_price:,.4f}\n"
        msg += f"标记价：${mark_price:,.4f}\n"
        msg += f"爆仓价：${liq_price:,.4f}\n"
        msg += "━━━━━━━━━━━━\n"
        msg += f"保证金：{margin:,.2f} USDT\n"
        msg += f"杠杆：{leverage}x\n"
        msg += f"收益率：{roe:+.2f}%\n"
        msg += f"未实现盈亏：{unrealized_pnl:+.2f} USDT\n"
        msg += "━━━━━━━━━━━━\n"
        msg += f"止盈：{tp_price}\n"
        msg += f"止损：{sl_price}"
        
        send_message(chat_id, msg)

def execute_trade(chat_id, symbol, side, dir_name, leverage, margin_usdt):
    lev_res = set_leverage(symbol, leverage)
    if not lev_res or lev_res.get("code") not in [None, 200]:
        send_message(chat_id, f"❌ 设置杠杆失败，请检查币种或 API 权限。")
        return

    price = get_current_price(symbol)
    if not price:
        send_message(chat_id, f"❌ 找不到币种 {symbol}，无法下单。")
        return

    quantity = round((margin_usdt * leverage) / price, 3)
    if quantity <= 0:
        send_message(chat_id, f"❌ 保证金过小，计算出的下单数量为 0。")
        return

    order_res = place_order(symbol, side, quantity)
    if order_res and "orderId" in order_res:
        msg = f"✅ 开仓成功！\n"
        msg += f"币种：{symbol}\n"
        msg += f"方向：{dir_name}\n"
        msg += f"杠杆：{leverage}x\n"
        msg += f"保证金：{margin_usdt:,.2f} USDT\n"
        msg += f"数量：{quantity}"
        send_message(chat_id, msg)
    else:
        error_msg = order_res.get("msg", "未知错误") if order_res else "请求失败"
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
                    msg += f"币种：{symbol}\n"
                    msg += f"当前价：${current_price:,.4f}\n"
                    msg += f"目标价：${target_price:,.4f}"
                    send_message(chat_id, msg)
                    
                    with LISTENER_LOCK:
                        if listener in LISTENERS:
                            LISTENERS.remove(listener)
                            
        except Exception as e:
            print(f"监听线程异常: {e}")
        
        time.sleep(5)

def handle_message(chat_id, text):
    raw_text = text.strip()
    
    # 1. 余额查询
    if raw_text == "myye":
        get_balance_info(chat_id)
        return
    
    # 2. 仓位情况查询
    if raw_text == "仓位情况":
        get_position_info(chat_id)
        return

    # 3. 价格监听
    listen_match = re.match(r'^监听\s*([a-zA-Z]+)\s*([0-9.]+)$', raw_text)
    if listen_match:
        symbol_str = listen_match.group(1).upper()
        target_price_str = listen_match.group(2)
        
        if not symbol_str.endswith("USDT"):
            symbol_str += "USDT"
            
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

    # 4. 极简开仓指令
    normalized_text = raw_text.replace("，", ",").replace(" ", ",")
    parts = [p for p in normalized_text.split(",") if p]

    if len(parts) == 4:
        symbol = parts[0].upper()
        if not symbol.endswith("USDT"):
            symbol += "USDT"
            
        lev_str = parts[1].lower().replace("x", "")
        if not lev_str.isdigit():
            return
        leverage = int(lev_str)
        
        if leverage <= 0 or leverage > 125:
            send_message(chat_id, "❌ 杠杆范围必须在 1-125 之间。")
            return
            
        direction = parts[2].lower()
        if direction in ["多", "long", "buy"]:
            side = "BUY"
            dir_name = "做多"
        elif direction in ["空", "short", "sell"]:
            side = "SELL"
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
