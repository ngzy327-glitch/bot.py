import os
import re
import time
import threading
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ==========================
# 本地模拟账户数据
# ==========================
BALANCE = 1000.0   # 初始资金 1000 USDT
POSITIONS = []     # 当前持仓
POS_LOCK = threading.Lock()

LST = []
LST_LOCK = threading.Lock()

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
    """使用 OKX 公开行情接口获取价格，无需 API Key"""
    inst_id = f"{symbol.upper()}-USDT"
    try:
        url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
        resp = requests.get(url, timeout=5).json()
        if resp.get("code") == "0" and resp.get("data"):
            return float(resp["data"][0]["last"])
    except Exception as e:
        print(f"获取 {symbol} 行情失败: {e}")
    return None

def get_balance_info(chat_id):
    """查询余额"""
    total_pnl = 0.0
    with POS_LOCK:
        current_positions = list(POSITIONS)
    
    for pos in current_positions:
        price = get_current_price(pos["symbol"])
        if price:
            if pos["side"] == "多":
                pnl = (price - pos["entry_price"]) * pos["qty"]
            else:
                pnl = (pos["entry_price"] - price) * pos["qty"]
            total_pnl += pnl

    msg = f"💰 模拟账户余额\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"可用资金：{BALANCE:,.2f} USDT\n"
    msg += f"未实现盈亏：{total_pnl:+,.2f} USDT\n"
    msg += f"总权益：{BALANCE + total_pnl:,.2f} USDT"
    send_message(chat_id, msg)

def get_position_info(chat_id):
    """查询持仓"""
    with POS_LOCK:
        current_positions = list(POSITIONS)
    
    if not current_positions:
        send_message(chat_id, "📭 当前无持仓。")
        return

    for pos in current_positions:
        price = get_current_price(pos["symbol"])
        if not price:
            continue

        if pos["side"] == "多":
            pnl = (price - pos["entry_price"]) * pos["qty"]
            liq_price = pos["entry_price"] * (1 - 1 / pos["leverage"])
        else:
            pnl = (pos["entry_price"] - price) * pos["qty"]
            liq_price = pos["entry_price"] * (1 + 1 / pos["leverage"])

        roe = (pnl / pos["margin"]) * 100 if pos["margin"] > 0 else 0.0
        direction = "多 🟢" if pos["side"] == "多" else "空 🔴"

        msg = f"📊 {pos['symbol']} 持仓\n"
        msg += "━━━━━━━━━━━━\n"
        msg += f"方向：{direction}\n"
        msg += f"持仓量：{pos['qty']:.4f}\n"
        msg += f"开仓价：${pos['entry_price']:,.4f}\n"
        msg += f"标记价：${price:,.4f}\n"
        msg += f"爆仓价：${liq_price:,.4f}\n"
        msg += "━━━━━━━━━━━━\n"
        msg += f"保证金：{pos['margin']:,.2f} USDT\n"
        msg += f"杠杆：{pos['leverage']}x\n"
        msg += f"收益率：{roe:+.2f}%\n"
        msg += f"未实现盈亏：{pnl:+,.2f} USDT"
        send_message(chat_id, msg)

def open_position(chat_id, symbol, side, dir_name, leverage, margin_usdt):
    """开仓"""
    global BALANCE
    
    if margin_usdt > BALANCE:
        send_message(chat_id, f"❌ 保证金不足！当前可用：{BALANCE:,.2f} USDT")
        return

    price = get_current_price(symbol)
    if not price:
        send_message(chat_id, f"❌ 无法获取 {symbol} 行情，请检查币种。")
        return

    qty = (margin_usdt * leverage) / price
    
    with POS_LOCK:
        for p in POSITIONS:
            if p["symbol"] == symbol.upper():
                send_message(chat_id, f"⚠️ 已有 {symbol.upper()} 持仓，请先平仓。")
                return
        
        BALANCE -= margin_usdt
        POSITIONS.append({
            "symbol": symbol.upper(),
            "side": dir_name,
            "leverage": leverage,
            "margin": margin_usdt,
            "entry_price": price,
            "qty": qty
        })

    msg = f"✅ 模拟开仓成功！\n"
    msg += f"币种：{symbol.upper()}\n"
    msg += f"方向：{dir_name}\n"
    msg += f"杠杆：{leverage}x\n"
    msg += f"保证金：{margin_usdt:,.2f} USDT\n"
    msg += f"开仓价：${price:,.4f}\n"
    msg += f"数量：{qty:.4f}"
    send_message(chat_id, msg)

def close_position(chat_id, symbol):
    """平仓"""
    global BALANCE
    symbol = symbol.upper()

    with POS_LOCK:
        pos = None
        for p in POSITIONS:
            if p["symbol"] == symbol:
                pos = p
                break
        
        if not pos:
            send_message(chat_id, f"📭 未找到 {symbol} 的持仓。")
            return

        price = get_current_price(symbol)
        if not price:
            send_message(chat_id, "❌ 无法获取行情，平仓失败。")
            return

        if pos["side"] == "多":
            pnl = (price - pos["entry_price"]) * pos["qty"]
        else:
            pnl = (pos["entry_price"] - price) * pos["qty"]

        return_amount = pos["margin"] + pnl
        BALANCE += return_amount
        POSITIONS.remove(pos)

    msg = f"✅ 平仓成功！\n"
    msg += f"币种：{symbol}\n"
    msg += f"方向：{pos['side']}\n"
    msg += f"开仓价：${pos['entry_price']:,.4f}\n"
    msg += f"平仓价：${price:,.4f}\n"
    msg += f"盈亏：{pnl:+,.2f} USDT\n"
    msg += f"返还金额：{return_amount:,.2f} USDT"
    send_message(chat_id, msg)

def price_monitor_worker():
    print("价格监听线程已启动...")
    while True:
        try:
            with LST_LOCK:
                current = list(LST)
            for listener in current:
                symbol = listener["symbol"]
                target = listener["target_price"]
                chat_id = listener["chat_id"]

                price = get_current_price(symbol)
                if price is None:
                    continue

                triggered = False
                if target > price:
                    if price >= target:
                        triggered = True
                else:
                    if price <= target:
                        triggered = True

                if triggered:
                    msg = f"🚨 价格提醒！\n"
                    msg += f"币种：{symbol.upper()}\n"
                    msg += f"当前价：${price:,.4f}\n"
                    msg += f"目标价：${target:,.4f}"
                    send_message(chat_id, msg)

                    with LST_LOCK:
                        if listener in LST:
                            LST.remove(listener)
        except Exception as e:
            print(f"监听线程异常: {e}")
        time.sleep(30)

def handle_message(chat_id, text):
    global BALANCE
    raw_text = text.strip()

    # 1. 余额查询
    if raw_text == "myye":
        get_balance_info(chat_id)
        return

    # 2. 充值指令：充值1000
    recharge_match = re.match(r'^充值\s*([0-9.]+)$', raw_text)
    if recharge_match:
        try:
            amount = float(recharge_match.group(1))
            if amount > 0:
                BALANCE += amount
                send_message(chat_id, f"💰 充值成功！当前可用余额：{BALANCE:,.2f} USDT")
        except ValueError:
            pass
        return

    # 3. 持仓查询
    if raw_text == "仓位情况":
        get_position_info(chat_id)
        return

    # 4. 平仓指令：平仓btc
    close_match = re.match(r'^平仓\s*([a-zA-Z]+)$', raw_text)
    if close_match:
        close_position(chat_id, close_match.group(1))
        return

    # 5. 开仓指令：btc，100x，多，300
    normalized_text = raw_text.replace("，", ",").replace(" ", ",")
    parts = [p for p in normalized_text.split(",") if p]

    if len(parts) == 4:
        symbol = parts[0].upper()
        lev_str = parts[1].lower().replace("x", "")
        if not lev_str.isdigit():
            return
        leverage = int(lev_str)
        if leverage <= 0 or leverage > 125:
            send_message(chat_id, "❌ 杠杆范围必须在 1-125 之间。")
            return
        direction = parts[2].lower()
        if direction in ["多", "long", "buy"]:
            dir_name = "多"
        elif direction in ["空", "short", "sell"]:
            dir_name = "空"
        else:
            return
        try:
            margin_usdt = float(parts[3])
        except ValueError:
            return
        if margin_usdt <= 0:
            send_message(chat_id, "❌ 保证金必须大于 0。")
            return
        open_position(chat_id, symbol, dir_name, dir_name, leverage, margin_usdt)
        return

    return

def main():
    if not ALLOWED_USER_ID:
        print("警告：未设置 ALLOWED_USER_ID，机器人将对所有人开放！")
    else:
        print(f"权限控制已开启，只允许 User ID: {ALLOWED_USER_ID} 操作。")

    t = threading.Thread(target=price_monitor_worker, daemon=True)
    t.start()

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
