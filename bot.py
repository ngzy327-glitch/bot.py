import os
import re
import time
import random
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

# ==========================
# 广播控制与时间记录
# ==========================
BROADCAST_ENABLED = True
BROADCAST_INTERVAL = 900  # 15分钟 = 900秒
LAST_BROADCAST_TIME = time.time()
LAST_ACTIVITY_TIME = time.time()
ACTIVITY_LOCK = threading.Lock()
IDLE_NOTIFIED = False  # 记录是否已发送过15分钟无操作提醒

# ==========================
# 情绪价值语料库（60条）
# ==========================
EMOTIONAL_MESSAGES = [
    "主人，盯盘辛苦啦，喝口水，揉揉眼睛吧！👀",
    "稳住，别慌，市场永远是对的，我们要做的是顺势而为。🌊",
    "行情总在绝望中诞生，在半信半疑中成长。💡",
    "叮咚！您的贴身交易管家提醒您：该起来活动一下啦！🚶‍♂️",
    "亏钱了别难过，被市场毒打是每个大佬的必经之路。💪",
    "做交易最重要的是活着，只要还在牌桌上，就有翻盘的机会！🃏",
    "主人，今天有严格执行自己的交易计划吗？自律即自由！🎯",
    "浮盈浮亏都是数字，落袋为安才是真金白银。💰",
    "重仓一时爽，爆仓火葬场。主人，仓位管理千万不能忘！⚖️",
    "一入币圈深似海，从此休息是路人。记得劳逸结合哦～ 🌴",
    "主人，看K线累了吗？闭上眼睛深呼吸三次，世界如此美好。🧘",
    "不贪不惧，耐心等待属于你的那个击球点。⚾",
    "交易是一场修行，修的是心，行的是道。🧘‍♂️",
    "主人，不管今天盈亏如何，你都是最棒的！⭐",
    "别人贪婪我恐惧，别人恐惧我贪婪。现在市场是什么情绪？🧐",
    "叮！该喝水了主人，身体是革命的本钱！🥤",
    "频繁操作是亏损的源泉，学会空仓也是一种智慧。🛑",
    "止损永远是对的，哪怕事后看是错的。🛡️",
    "主人，深夜盯盘伤身体，早点休息，明天再战！🌙",
    "牛市赚钱，熊市赚币，震荡市赚经验。📈",
    "只有退潮了，才知道谁在裸泳。控制杠杆！🩲",
    "主人，你现在是空仓、多单还是空单呀？来跟我聊聊吧～ 💬",
    "别让情绪左右你的交易，冷静，客观。🧊",
    "每一次亏损都是一次宝贵的经验，复盘总结，下次避坑。📝",
    "财富是认知的变现，提升认知比看盘更重要。🧠",
    "主人，行情不好就休息，不要强行交易。🏖️",
    "保持耐心，市场永远不缺机会，缺的是本金。💎",
    "叮咚！你的专属客服上线啦，今天心情怎么样？😊",
    "交易不是生活的全部，多陪陪家人朋友吧。👨‍👩‍👧",
    "顺势轻仓止损，这六个字值千金。🏆",
    "主人，要不要吃个夜宵补充一下能量？🍜",
    "横盘的时候最考验耐心，熬过去就是星辰大海。🌌",
    "别总想着一夜暴富，慢慢变富才是最快的路。🚶",
    "市场永远是对的，错的是我们的预期。🤷",
    "做多怕跌，做空怕涨，空仓怕踏空。这是你吗？😅",
    "主人，你已经很优秀了，给自己一点信心！✨",
    "记住，你是来赚钱的，不是来寻刺激的。🎯",
    "浮亏加仓是大忌，千万不要逆势抗单！🚫",
    "祝主人多空双吃，天天盈利！🧧",
    "行情来了就上，行情走了就撤，不拖泥带水。⚔️",
    "主人，今天看盘有没有被行情气到？深呼吸～ 😮‍💨",
    "机会是等出来的，不是频繁操作出来的。⏳",
    "钱不入急门，慢慢来，比较快。🐢",
    "你现在的持仓，晚上能睡个好觉吗？如果能，就是好仓位。😴",
    "叮！该起来走动走动了，久坐对颈椎不好哦。🚶‍♀️",
    "胜利属于最能忍耐的人。坚持你的交易系统！💪",
    "交易的真谛：截断亏损，让利润奔跑。🏃‍♂️",
    "主人，无论行情多疯狂，都要保留一份清醒。🧠",
    "我们的目标不是每次都对，而是总体盈利。📊",
    "偶尔离开屏幕，你会发现世界更宽广。🌅",
    "主人，如果感到焦虑，说明仓位重了。减仓保平安！✂️",
    "别拿生活费来炒币，用闲钱投资才能心态平和。💵",
    "亏损是交易的一部分，接受它，然后放下它。🍃",
    "市场每天都在开门，不要急于一时的得失。🚪",
    "主人，我给你加油打气啦，冲冲冲！📣",
    "交易系统要简单，执行力要强悍。⚙️",
    "别人恐慌的时候，你在做什么？🤔",
    "叮！您的情绪价值补给包已送达，请查收！🎁",
    "稳住心态，我们能赢！相信自己，相信趋势。🏆",
    "主人，今天也要元气满满地交易哦！☀️"
]

# 用于不重复随机抽取的消息池
MESSAGE_POOL = EMOTIONAL_MESSAGES.copy()
POOL_LOCK = threading.Lock()

def get_random_message():
    global MESSAGE_POOL
    with POOL_LOCK:
        if not MESSAGE_POOL:
            MESSAGE_POOL = EMOTIONAL_MESSAGES.copy()
        msg = random.choice(MESSAGE_POOL)
        MESSAGE_POOL.remove(msg)
        return msg

# ==========================
# 基础函数
# ==========================
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
    inst_id = f"{symbol.upper()}-USDT"
    try:
        url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
        resp = requests.get(url, timeout=5).json()
        if resp.get("code") == "0" and resp.get("data"):
            return float(resp["data"][0]["last"])
    except:
        pass
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
    
    total_equity = BALANCE + total_pnl
    msg = f"💰 账户余额\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"可用资金：{BALANCE:,.2f} USDT\n"
    msg += f"未实现盈亏：{total_pnl:+,.2f} USDT\n"
    msg += f"总权益：{total_equity:,.2f} USDT"
    send_message(chat_id, msg)

def get_position_info(chat_id):
    with POS_LOCK:
        current_positions = list(POSITIONS)
    if not current_positions:
        send_message(chat_id, "📭 当前无持仓。空仓也是一种智慧，等待最佳击球点！")
        return
    for pos in current_positions:
        price = get_current_price(pos["symbol"])
        if not price: continue
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
        send_message(chat_id, "📭 暂无历史交易记录。你是刚踏入战场的萌新吗？")
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

# ==========================
# 核心交易与情绪化回复
# ==========================
def open_position(chat_id, symbol, side, dir_name, leverage, margin_usdt):
    global BALANCE
    if margin_usdt > BALANCE:
        send_message(chat_id, f"❌ 保证金不足！当前可用：{BALANCE:,.2f} USDT。要不先去充值一波？")
        return
    price = get_current_price(symbol)
    if not price:
        send_message(chat_id, f"❌ 无法获取 {symbol} 行情，网络卡了吗？")
        return
    qty = (margin_usdt * leverage) / price
    with POS_LOCK:
        for p in POSITIONS:
            if p["symbol"] == symbol.upper():
                send_message(chat_id, f"⚠️ 已有 {symbol.upper()} 持仓，请先平仓。不要贪杯哦！")
                return
        BALANCE -= margin_usdt
        POSITIONS.append({
            "symbol": symbol.upper(),
            "side": dir_name,
            "leverage": leverage,
            "margin": margin_usdt,
            "entry_price": price,
            "qty": qty,
            "chat_id": chat_id,
            "notified_win": False,
            "notified_loss": False
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
            send_message(chat_id, f"📭 未找到 {symbol} 的持仓。你是不是记错了？")
            return
        price = get_current_price(symbol)
        if not price:
            send_message(chat_id, "❌ 无法获取行情，平仓失败。稍后再试吧！")
            return
        if pos["side"] == "多":
            pnl = (price - pos["entry_price"]) * pos["qty"]
        else:
            pnl = (pos["entry_price"] - price) * pos["qty"]
        return_amount = pos["margin"] + pnl
        BALANCE += return_amount
        POSITIONS.remove(pos)
        with HISTORY_LOCK:
            TRADE_HISTORY.append({"symbol": symbol, "side": pos["side"], "pnl": pnl})
            
    msg = f"✅ 平仓成功！\n"
    msg += f"币种：{symbol}\n"
    msg += f"方向：{pos['side']}\n"
    msg += f"盈亏：{pnl:+,.2f} USDT\n"
    msg += f"返还金额：{return_amount:,.2f} USDT"
    send_message(chat_id, msg)

def trigger_liquidation(symbol, price, pos):
    with POS_LOCK:
        if pos in POSITIONS: POSITIONS.remove(pos)
    with HISTORY_LOCK:
        TRADE_HISTORY.append({"symbol": symbol, "side": pos["side"], "pnl": -pos["margin"]})
    
    msg = f"🔔 菜狗你仓位炸了\n"
    msg += "━━━━━━━━━━━━\n"
    msg += f"币种：{symbol}\n"
    msg += f"方向：{pos['side']}\n"
    msg += f"损失保证金：{pos['margin']:,.2f} USDT"
    send_message(pos["chat_id"], msg)

def withdraw_balance(chat_id, amount_str):
    global BALANCE
    try: amount = float(amount_str)
    except ValueError: return
    if amount <= 0 or amount > BALANCE:
        send_message(chat_id, "❌ 提现金额不合法或余额不足！")
        return
    BALANCE -= amount
    send_message(chat_id, f"✅ 提现成功！落袋为安。\n提现金额：{amount:,.2f} USDT\n当前余额：{BALANCE:,.2f} USDT")

def price_monitor_worker():
    while True:
        try:
            with LST_LOCK: current = list(LST)
            for listener in current:
                symbol = listener["symbol"]; target = listener["target_price"]; chat_id = listener["chat_id"]
                price = get_current_price(symbol)
                if price is None: continue
                triggered = False
                if target > price and price >= target: triggered = True
                elif target <= price and price <= target: triggered = True
                if triggered:
                    msg = f"🚨 价格提醒！你等的那个价格到了！\n币种：{symbol.upper()}\n当前价：${price:,.4f}"
                    send_message(chat_id, msg)
                    with LST_LOCK:
                        if listener in LST: LST.remove(listener)
        except Exception as e: print(f"监听线程异常: {e}")
        time.sleep(30)

# ==========================
# 后台监控线程（爆仓、盈亏±50%、定时广播、15分钟提醒）
# ==========================
def background_worker(chat_id):
    global LAST_BROADCAST_TIME, LAST_ACTIVITY_TIME, IDLE_NOTIFIED
    print("后台监控与广播线程已启动...")
    while True:
        try:
            current_time = time.time()
            with POS_LOCK:
                current_positions = list(POSITIONS)
            
            # 1. 15分钟定时情绪价值播报
            if BROADCAST_ENABLED and (current_time - LAST_BROADCAST_TIME >= BROADCAST_INTERVAL):
                msg = get_random_message()
                send_message(chat_id, f"📢 {msg}")
                LAST_BROADCAST_TIME = current_time

            # 2. 15分钟无操作提醒（独立于广播，不重置活动时间，用状态开关控制）
            with ACTIVITY_LOCK:
                idle_time = current_time - LAST_ACTIVITY_TIME
            
            if current_positions and idle_time >= 15 * 60 and not IDLE_NOTIFIED:
                mood_msg = get_random_message()
                send_message(chat_id, f"⏰ 主人，你已经15分钟没操作啦！{mood_msg}")
                IDLE_NOTIFIED = True  # 标记已提醒，避免重复轰炸

            # 3. 爆仓及盈亏 ±50% 检查
            for pos in current_positions:
                price = get_current_price(pos["symbol"])
                if price is None: continue
                
                if pos["side"] == "多":
                    pnl = (price - pos["entry_price"]) * pos["qty"]
                    liq_price = pos["entry_price"] * (1 - 1 / pos["leverage"])
                else:
                    pnl = (pos["entry_price"] - price) * pos["qty"]
                    liq_price = pos["entry_price"] * (1 + 1 / pos["leverage"])
                
                roe = (pnl / pos["margin"]) * 100 if pos["margin"] > 0 else 0.0
                
                if pos["side"] == "多" and price <= liq_price:
                    trigger_liquidation(pos["symbol"], price, pos); continue
                if pos["side"] == "空" and price >= liq_price:
                    trigger_liquidation(pos["symbol"], price, pos); continue

                if roe >= 50 and not pos.get("notified_win"):
                    send_message(pos["chat_id"], "⏰ 主人，该回来看看仓位啦！当前已盈利 50%+，考虑止盈吗？🚀")
                    with POS_LOCK:
                        if pos in POSITIONS: pos["notified_win"] = True
                            
                if roe <= -50 and not pos.get("notified_loss"):
                    send_message(pos["chat_id"], "⏰ 主人，该回来看看仓位啦！当前已亏损 50%，注意风险控制！🩸")
                    with POS_LOCK:
                        if pos in POSITIONS: pos["notified_loss"] = True

        except Exception as e:
            print(f"后台监控异常: {e}")
        time.sleep(5)

def handle_message(chat_id, text):
    global BALANCE, LAST_ACTIVITY_TIME, BROADCAST_ENABLED, LAST_BROADCAST_TIME, IDLE_NOTIFIED
    raw_text = text.strip()
    
    # ================= 欢迎回家逻辑 =================
    current_time = time.time()
    with ACTIVITY_LOCK:
        idle_time = current_time - LAST_ACTIVITY_TIME
        LAST_ACTIVITY_TIME = current_time  # 先更新最后活动时间
    
    # 如果超过5分钟（300秒）没说话，触发欢迎语
    if idle_time >= 300:
        send_message(chat_id, "欢迎主人回家🥰")
        IDLE_NOTIFIED = False  # 重置状态，这样15分钟后还能再次提醒

    # 广播控制
    if raw_text == "开启播报":
        BROADCAST_ENABLED = True
        LAST_BROADCAST_TIME = time.time()
        send_message(chat_id, "🔊 情绪价值播报已开启！每15分钟我会准时出现～")
        return
    if raw_text == "关闭播报":
        BROADCAST_ENABLED = False
        send_message(chat_id, "🔇 情绪价值播报已关闭。需要我时再叫我。")
        return

    if raw_text.endswith(".") or raw_text.endswith("。"):
        symbol = raw_text[:-1].strip().upper()
        if symbol.isalpha() and 2 <= len(symbol) <= 10:
            info = get_current_price(symbol)
            if info:
                send_message(chat_id, f"📊 {symbol} 行情\n💰 价格：${info:,.4f}\n")
        return

    if raw_text == "myye":
        get_balance_info(chat_id)
        return

    if raw_text == "战绩":
        get_trade_history(chat_id)
        return

    if raw_text == "仓位情况":
        get_position_info(chat_id)
        return

    if raw_text.startswith("监听"):
        match = re.match(r'^监听\s*([a-zA-Z]+)\s*([0-9.]+)$', raw_text)
        if match:
            symbol_str, target_price_str = match.group(1).upper(), match.group(2)
            try: target_price = float(target_price_str)
            except: return
            with LST_LOCK: LST.append({"symbol": symbol_str, "target_price": target_price, "chat_id": chat_id})
            send_message(chat_id, f"✅ 已开启监听：{symbol_str} 达到 ${target_price:,.4f} 时通知你。\n💬 眼睛瞪得像铜铃，我替你盯着！")
        return

    if raw_text.startswith("充值"):
        match = re.match(r'^充值\s*([0-9.]+)$', raw_text)
        if match:
            try: amount = float(match.group(1))
            except: return
            if amount > 0:
                BALANCE += amount
                send_message(chat_id, f"💰 充值成功！资金已到位，冲！\n当前余额：{BALANCE:,.2f} USDT")
        return

    if raw_text.startswith("提现"):
        match = re.match(r'^提现\s*([0-9.]+)$', raw_text)
        if match: withdraw_balance(chat_id, match.group(1))
        return

    if raw_text.startswith("平仓"):
        match = re.match(r'^平仓\s*([a-zA-Z]+)$', raw_text)
        if match: close_position(chat_id, match.group(1))
        return

    # 开仓指令
    normalized_text = raw_text.replace("，", ",").replace(" ", ",")
    parts = [p for p in normalized_text.split(",") if p]
    if len(parts) == 4:
        symbol = parts[0].upper(); lev_str = parts[1].lower().replace("x", "")
        if not lev_str.isdigit(): return
        leverage = int(lev_str)
        if leverage <= 0 or leverage > 125: return
        direction = parts[2].lower()
        if direction in ["多", "long", "buy"]: dir_name = "多"
        elif direction in ["空", "short", "sell"]: dir_name = "空"
        else: return
        try: margin_usdt = float(parts[3])
        except: return
        if margin_usdt > 0: open_position(chat_id, symbol, dir_name, dir_name, leverage, margin_usdt)
        return

def main():
    if not ALLOWED_USER_ID:
        print("警告：未设置 ALLOWED_USER_ID，机器人将对所有人开放！")
    else:
        print(f"权限控制已开启，只允许 User ID: {ALLOWED_USER_ID} 操作。")
    
    t1 = threading.Thread(target=background_worker, args=(ALLOWED_USER_ID,), daemon=True); t1.start()
    t2 = threading.Thread(target=price_monitor_worker, daemon=True); t2.start()
    
    print("Bot 已启动...")
    offset = None
    while True:
        updates = get_updates(offset)
        if "result" in updates:
            for update in updates["result"]:
                offset = update["update_id"] + 1
                message = update.get("message")
                if not message: continue
                if ALLOWED_USER_ID:
                    from_user = message.get("from", {})
                    if str(from_user.get("id", "")) != ALLOWED_USER_ID: continue
                chat_id = message["chat"]["id"]
                text = message.get("text", "")
                if text: handle_message(chat_id, text)
        time.sleep(1)

if __name__ == "__main__":
    main()
