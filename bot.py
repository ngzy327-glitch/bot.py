import os
import re
import time
import threading
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ==========================
# 本地账户数据
# ==========================
BALANCE = 1000.0
POSITIONS = []
POS_LOCK = threading.Lock()

TRADE_HISTORY = []
HISTORY_LOCK = threading.Lock()

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
    """获取实时价格，优先 OKX，备选 Binance"""
    inst_id = f"{symbol.upper()}-USDT"
    try:
        url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
        resp = requests.get(url, timeout=5).json()
        if resp.get("code") == "0" and resp.get("data"):
            price = float(resp["data"][0]["last"])
            print(f"[行情] OKX 返回 {symbol} 价格: {price}")
            return price
    except Exception as e:
        print(f"[行情] OKX 获取 {symbol} 失败: {e}")
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}USDT"
        resp = requests.get(url, timeout=5).json()
        if "price" in resp:
            price = float(resp["price"])
            print(f"[行情] Binance 返回 {symbol} 价格: {price}")
            return price
    except Exception as e:
        print(f"[行情] Binance 获取 {symbol} 失败: {e}")
    return None

def get_crypto_info(symbol):
    """获取行情详情（价格+涨跌幅）"""
    inst_id = f"{symbol.upper()}-USDT"
    try:
        url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
        resp = requests.get(url, timeout=5).json()
        if resp.get("code") == "0" and resp.get("data"):
            data = resp["data"][0]
            price = float(data["last"])
            open_24h = float(data["open24h"])
            c24 = ((price - open_24h) / open_24h) * 100 if open_24h else 0
            return {"price": price, "change_24h": c24, "change_7d": None}
    except:
        pass
    price = get_current_price(symbol)
    if price:
        return {"price": price, "change_24h": None, "change_7d": None}
    return None

def get_balance_info(chat_id):
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
    msg = f"💰 账户余额\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"可用资金：{BALANCE:,.2f} USDT\n"
    msg += f"未实现盈亏：{total_pnl:+,.2f} USDT\n"
    msg += f"总权益：{BALANCE + total_pnl:,.2f} USDT"
    send_message(chat_id, msg)

def get_position_info(chat_id):
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

def get_trade_history(chat_id):
    with HISTORY_LOCK:
        history = list(TRADE_HISTORY)
    if not history:
        send_message(chat_id, "📭 暂无历史交易记录。")
        return
    total_trades = len(history)
    total_pnl = sum(t["pnl"] for t in history)
    win_trades = [t for t in history if t["pnl"] > 0]
    loss_trades = [t for t in history if t["pnl"] <= 0]
    win_count = len(win_trades)
    loss_count = len(loss_trades)
    win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
    avg_win = sum(t["pnl"] for t in win_trades) / win_count if win_count > 0 else 0
    avg_loss = sum(t["pnl"] for t in loss_trades) / loss_count if loss_count > 0 else 0
    msg = f"📈 战绩报表\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"总交易次数：{total_trades} 次\n"
    msg += f"总盈亏：{total_pnl:+,.2f} USDT\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"胜率：{win_rate:.2f}%\n"
    msg += f"盈利次数：{win_count} 次\n"
    msg += f"亏损次数：{loss_count} 次\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"平均盈利：{avg_win:+,.2f} USDT\n"
    msg += f"平均亏损：{avg_loss:+,.2f} USDT"
    send_message(chat_id, msg)

def open_position(chat_id, symbol, side, dir_name, leverage, margin_usdt):
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
            "qty": qty,
            "chat_id": chat_id
        })
    msg = f"✅ 开仓成功！\n"
    msg += f"币种：{symbol.upper()}\n"
    msg += f"方向：{dir_name}\n"
    msg += f"杠杆：{leverage}x\n"
    msg += f"保证金：{margin_usdt:,.2f} USDT\n"
    msg += f"实时开仓价：${price:,.4f}\n"
    msg += f"数量：{qty:.4f}"
    send_message(chat_id, msg)

def close_position(chat_id, symbol):
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
        with HISTORY_LOCK:
            TRADE_HISTORY.append({
                "symbol": symbol,
                "side": pos["side"],
                "pnl": pnl
            })
    msg = f"✅ 平仓成功！\n"
    msg += f"币种：{symbol}\n"
    msg += f"方向：{pos['side']}\n"
    msg += f"开仓价：${pos['entry_price']:,.4f}\n"
    msg += f"实时平仓价：${price:,.4f}\n"
    msg += f"盈亏：{pnl:+,.2f} USDT\n"
    msg += f"返还金额：{return_amount:,.2f} USDT"
    send_message(chat_id, msg)

def trigger_liquidation(symbol, price, pos):
    """触发爆仓"""
    with POS_LOCK:
        if pos in POSITIONS:
            POSITIONS.remove(pos)
    with HISTORY_LOCK:
        TRADE_HISTORY.append({
            "symbol": symbol,
            "side": pos["side"],
            "pnl": -pos["margin"]
        })
    if pos["side"] == "多":
        liq_price = pos["entry_price"] * (1 - 1 / pos["leverage"])
    else:
        liq_price = pos["entry_price"] * (1 + 1 / pos["leverage"])
    msg = f"🔔菜狗你仓位炸了\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"币种：{symbol}\n"
    msg += f"方向：{pos['side']}\n"
    msg += f"开仓价：${pos['entry_price']:,.4f}\n"
    msg += f"爆仓价：${liq_price:,.4f}\n"
    msg += f"爆仓价格：${price:,.4f}\n"
    msg += f"损失保证金：{pos['margin']:,.2f} USDT"
    send_message(pos["chat_id"], msg)

def liquidation_checker():
    """爆仓检查线程，每5秒检查一次"""
    print("爆仓检查线程已启动...")
    while True:
        try:
            with POS_LOCK:
                current_positions = list(POSITIONS)
            for pos in current_positions:
                price = get_current_price(pos["symbol"])
                if price is None:
                    continue
                if pos["side"] == "多":
                    liq_price = pos["entry_price"] * (1 - 1 / pos["leverage"])
                    if price <= liq_price:
                        trigger_liquidation(pos["symbol"], price, pos)
                else:
                    liq_price = pos["entry_price"] * (1 + 1 / pos["leverage"])
                    if price >= liq_price:
                        trigger_liquidation(pos["symbol"], price, pos)
        except Exception as e:
            print(f"爆仓检查异常: {e}")
        time.sleep(5)

def withdraw_balance(chat_id, amount_str):
    global BALANCE
    try:
        amount = float(amount_str)
    except ValueError:
        return
    if amount <= 0:
        send_message(chat_id, "❌ 提现金额必须大于 0。")
        return
    if amount > BALANCE:
        send_message(chat_id, f"❌ 余额不足！当前可用：{BALANCE:,.2f} USDT")
        return
    BALANCE -= amount
    send_message(chat_id, f"✅ 提现成功！\n提现金额：{amount:,.2f} USDT\n当前可用余额：{BALANCE:,.2f} USDT")

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

    # 1. 行情查询
    if raw_text.endswith(".") or raw_text.endswith("。"):
        symbol = raw_text[:-1].strip().upper()
        if symbol.isalpha() and 2 <= len(symbol) <= 10:
            info = get_crypto_info(symbol)
            if info:
                msg = f"📊 {symbol} 行情\n"
                msg += "━━━━━━━━━━━━\n"
                msg += f"💰 价格：${info['price']:,.4f}\n"
                msg += "━━━━━━━━━━━━\n"
                if info.get("change_24h") is not None:
                    arrow = "📈" if info["change_24h"] >= 0 else "📉"
                    msg += f"{arrow} 24h涨跌：{info['change_24h']:+.2f}%\n"
                if info.get("change_7d") is not None:
                    arrow = "📈" if info["change_7d"] >= 0 else "📉"
                    msg += f"{arrow} 7d涨跌：{info['change_7d']:+.2f}%"
                send_message(chat_id, msg)
        return

    # 2. 监听指令
    listen_match = re.match(r'^监听\s*([a-zA-Z]+)\s*([0-9.]+)$', raw_text)
    if listen_match:
        symbol_str = listen_match.group(1).upper()
        target_price_str = listen_match.group(2)
        try:
            target_price = float(target_price_str)
        except ValueError:
            return
        if target_price <= 0:
            send_message(chat_id, "❌ 监听价格必须大于 0。")
            return
        with LST_LOCK:
            for listener in LST:
                if listener["symbol"] == symbol_str and listener["target_price"] == target_price:
                    send_message(chat_id, "⚠️ 该监听已存在。")
                    return
            LST.append({
                "symbol": symbol_str,
                "target_price": target_price,
                "chat_id": chat_id
            })
        send_message(chat_id, f"✅ 已开启监听：{symbol_str} 达到 ${target_price:,.4f} 时通知你。")
        return

    # 3. 余额查询
    if raw_text == "myye":
        get_balance_info(chat_id)
        return

    # 4. 充值
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

    # 5. 提现
    withdraw_match = re.match(r'^提现\s*([0-9.]+)$', raw_text)
    if withdraw_match:
        withdraw_balance(chat_id, withdraw_match.group(1))
        return

    # 6. 战绩
    if raw_text == "战绩":
        get_trade_history(chat_id)
        return

    # 7. 持仓查询
    if raw_text == "仓位情况":
        get_position_info(chat_id)
        return

    # 8. 平仓
    close_match = re.match(r'^平仓\s*([a-zA-Z]+)$', raw_text)
    if close_match:
        close_position(chat_id, close_match.group(1))
        return

    # 9. 开仓
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
    t1 = threading.Thread(target=price_monitor_worker, daemon=True)
    t1.start()
    t2 = threading.Thread(target=liquidation_checker, daemon=True)
    t2.start()
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
