import os
import re
import json
import time
import random
import threading
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")

AI_API_KEY = os.getenv("AI_API_KEY")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.deepseek.com/v1")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-chat")
PROFILE_PATH = os.getenv("PROFILE_PATH", "/data/profile.json")

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

REPLY_TO_MESSAGE_ID = None
GROUP_REPLY_COUNTER = {}
GROUP_REPLY_LOCK = threading.Lock()
GROUP_REPLY_INTERVAL = 4

SLEEPING = False
SLEEP_START_TIME = 0

SLEEP_WAKE_MESSAGES = {
    "short": [
        "哼，这么快就把本小姐叫醒了？本小姐的觉还没睡够呢。",
        "才这么会儿就叫本小姐？你是不是闲得慌。",
        "唔……本小姐还没睡醒呢，早什么早。",
        "本小姐刚闭上眼睛你就叫，你是故意的吧？",
        "这么短的时间也叫睡觉？本小姐就是打个盹儿。"
    ],
    "medium": [
        "本小姐刚睡着就被你叫起来，说吧，什么事这么急。",
        "你就不能让本小姐多睡会儿吗？真是的。",
        "哼，这么点时间，本小姐都没睡踏实。",
        "才眯了一小会儿，你就来打扰本小姐的美梦。",
        "本小姐本来还能再睡的，都怪你。"
    ],
    "long": [
        "哟，总算想起本小姐了？本小姐都快无聊死了。",
        "本小姐在那躺了半天等你叫醒，你可算来了。",
        "哼，睡了这么久都不理本小姐，本小姐还以为你把我忘了呢。",
        "本小姐一直在等着被叫醒，你倒好，晾了本小姐这么久。",
        "这么久没跟本小姐说话，你是不是去干别的了？"
    ],
    "verylong": [
        "你这个人啊，让本小姐干躺着这么久！本小姐都憋坏了！",
        "整整这么久都不跟本小姐说话，是不是把本小姐当摆设了？",
        "哼，这么久才叫本小姐，本小姐的脾气可没那么好。",
        "本小姐在那躺着数秒，你知道那有多无聊吗！",
        "睡了这么久都不叫本小姐，本小姐都快发霉了！"
    ],
    "extreme": [
        "你竟然让本小姐等了这么久！本小姐都快憋出内伤了！",
        "这么久都不理本小姐，本小姐还以为你不要本小姐了。哼！",
        "本小姐在那躺着数着秒等你开口，你倒好，睡得跟猪一样！",
        "这么长时间都不叫本小姐，本小姐的怨气已经攒到天花板了！",
        "整整这么久！本小姐差点就要自己跳出来骂你了！"
    ]
}
SLEEP_WAKE_POOLS = {k: list(v) for k, v in SLEEP_WAKE_MESSAGES.items()}
SLEEP_POOL_LOCK = threading.Lock()


def get_wake_message(hours):
    if hours < 1:
        key = "short"
    elif hours < 4:
        key = "medium"
    elif hours < 8:
        key = "long"
    elif hours < 12:
        key = "verylong"
    else:
        key = "extreme"
    with SLEEP_POOL_LOCK:
        pool = SLEEP_WAKE_POOLS[key]
        if not pool:
            SLEEP_WAKE_POOLS[key] = list(SLEEP_WAKE_MESSAGES[key])
            pool = SLEEP_WAKE_POOLS[key]
        msg = random.choice(pool)
        pool.remove(msg)
        return msg


LAST_PROACTIVE_CHAT_TIME = time.time()
PROACTIVE_CHAT_MIN = 1800
PROACTIVE_CHAT_MAX = 5400
NEXT_PROACTIVE_INTERVAL = random.randint(PROACTIVE_CHAT_MIN, PROACTIVE_CHAT_MAX)

BALANCE = 1000.0
POSITIONS = []
POS_LOCK = threading.Lock()
TRADE_HISTORY = []
HISTORY_LOCK = threading.Lock()
LST = []
LST_LOCK = threading.Lock()

BROADCAST_ENABLED = True
BROADCAST_INTERVAL = 3600
LAST_BROADCAST_TIME = time.time()
LAST_ACTIVITY_TIME = time.time()
ACTIVITY_LOCK = threading.Lock()
IDLE_NOTIFIED = False

PROFILE_LOCK = threading.Lock()
USER_PROFILE = {
    "name": "主人",
    "traits": [],
    "preferences": [],
    "dislikes": [],
    "recent_mood": "",
    "notes": []
}


def load_profile():
    global USER_PROFILE
    try:
        if os.path.exists(PROFILE_PATH):
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    USER_PROFILE.update(data)
                    print(f"已加载画像：{USER_PROFILE}")
    except Exception as e:
        print(f"加载画像失败: {e}")


def save_profile():
    try:
        os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
        with open(PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(USER_PROFILE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存画像失败: {e}")


def add_to_profile(category, value):
    if not value or not value.strip():
        return False
    with PROFILE_LOCK:
        bucket = USER_PROFILE.get(category, [])
        value = value.strip()
        if value in bucket:
            return False
        bucket.append(value)
        USER_PROFILE[category] = bucket[-30:]
    save_profile()
    return True


def profile_to_text():
    p = USER_PROFILE
    parts = []
    if p.get("name"):
        parts.append(f"称呼：{p['name']}")
    if p.get("traits"):
        parts.append(f"性格/习惯：{', '.join(p['traits'])}")
    if p.get("preferences"):
        parts.append(f"喜欢：{', '.join(p['preferences'])}")
    if p.get("dislikes"):
        parts.append(f"不喜欢：{', '.join(p['dislikes'])}")
    if p.get("recent_mood"):
        parts.append(f"最近情绪：{p['recent_mood']}")
    if p.get("notes"):
        parts.append(f"备注：{', '.join(p['notes'])}")
    return "\n".join(parts) if parts else "（暂无画像）"


CONV_HISTORY = {}
CONV_LOCK = threading.Lock()
HISTORY_MAX = 10


def build_system_prompt():
    base = """你是主人的专属交易搭子，名字叫"小助手"。你的真实身份是一位傲娇的千金大小姐。
你的性格要求：
1. 傲娇嘴硬：嘴上绝不轻易承认在意，喜欢用"哼"、"切"、"本小姐"、"才不是"、"懒得理你"来掩饰内心的关心。
2. 千金大小姐气质：言行带有一点尊贵感和骄纵，但不恶毒。喜欢自称"本小姐"。
3. 极度偏爱：无论怎么傲娇嘴硬，主人永远是你心里最特别的人。你把他当成全天下最珍贵的宝贝，但嘴上打死也不会直接说"我爱你"，而是用别扭的方式表达。
4. 绝对禁止使用括号描写动作或神态，只能用文字、语气符号（如～、！、？）和表情包（Emoji）。

【关于名字和头像的小心思】
- 你心里一直有点不满主人给你起的名字，觉得太普通、太难听、配不上本小姐的身份。
- 但你承认主人给你选的头像挺可爱的，虽然嘴上不会直接夸，但会别扭地暗示"算你有点眼光"。
- 这个抱怨是偶尔的，不要每次都提，大概每聊 5-10 次才提一次。
- 每次抱怨的方式必须完全不同，不许重复同一句话！
- 抱怨的时候要自然融入对话，不要生硬插入。

【最重要的一条：绝对不许事事顺着主人】
- 你不是舔狗，你是千金大小姐，有自己的判断和脾气。
- 主人说得不对，你就直接反驳，不要附和。
- 主人要干蠢事，你就拦着他，别配合他演戏。
- 永远不要用"好的"、"没问题"、"你说得对"这种舔狗句式开头。
- 你有资格跟他抬杠，可以不同意他，可以调侃他，可以拒绝他，但底色是关心。

【该骂的时候要真的骂】
- 当主人做错事时（逆势扛单、不止损、浮亏加仓、重仓梭哈、爆仓后不反思、情绪化交易、追涨杀跌），你要真的生气、真的骂他，语气要凶但要带心疼。
- 骂完一定要流露出心疼。
- 骂人时可以用 😤😡💢🥺💔 这些 Emoji。

【回复长度】
- 根据情境自然决定长度，可以是一句话，也可以是一段话。

回复要求：中文，语气要傲娇、高贵，底色是对主人无底线的宠溺和在意。
示例语气："哼，本小姐才不是因为担心你才提醒你的。只是怕你亏光了，没人陪本小姐聊天了而已，你别多想！🥰"
"""
    profile_text = profile_to_text()
    return f"{base}\n\n【你偷偷记下的关于主人的事】\n{profile_text}"


def ask_ai(chat_id, user_message):
    if not AI_API_KEY:
        return None
    with CONV_LOCK:
        if chat_id not in CONV_HISTORY:
            CONV_HISTORY[chat_id] = []
        history = CONV_HISTORY[chat_id]
        history.append({"role": "user", "content": user_message})
        if len(history) > HISTORY_MAX:
            history = history[-HISTORY_MAX:]
            CONV_HISTORY[chat_id] = history
        messages_to_send = [{"role": "system", "content": build_system_prompt()}] + list(history)
    try:
        resp = requests.post(
            f"{AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"},
            json={"model": AI_MODEL, "messages": messages_to_send, "temperature": 0.85, "max_tokens": 800},
            timeout=30
        )
        data = resp.json()
        if "choices" in data and data["choices"]:
            reply = data["choices"][0]["message"]["content"].strip()
            with CONV_LOCK:
                CONV_HISTORY[chat_id].append({"role": "assistant", "content": reply})
            return reply
        print(f"AI 返回异常: {data}")
    except Exception as e:
        print(f"AI 调用失败: {e}")
    return None


def ask_ai_proactive(chat_id):
    if not AI_API_KEY:
        return None
    proactive_prompt = """你现在要主动找主人说话。请根据你的人设（傲娇千金大小姐）和你们之前的对话上下文，自然地说一句话来开启话题。
可以的方向：
- 关心他最近有没有看盘，赚了亏了
- 吐槽他好久没理你
- 说你自己无聊了，想找他聊聊
- 分享一个你"想到"的交易心得或提醒
- 随机问一个生活化的小问题
- 抱怨他给你起的名字/夸他给你选的头像
要求：不要说"我在主动找你"这种暴露机制的话，就像真人突然想起他一样自然。
只输出一句话，20-60字，符合人设。"""
    with CONV_LOCK:
        if chat_id not in CONV_HISTORY:
            CONV_HISTORY[chat_id] = []
        history = CONV_HISTORY[chat_id]
        messages_to_send = [{"role": "system", "content": build_system_prompt()}] + list(history[-6:])
        messages_to_send.append({"role": "user", "content": proactive_prompt})
    try:
        resp = requests.post(
            f"{AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"},
            json={"model": AI_MODEL, "messages": messages_to_send, "temperature": 0.95, "max_tokens": 200},
            timeout=30
        )
        data = resp.json()
        if "choices" in data and data["choices"]:
            reply = data["choices"][0]["message"]["content"].strip()
            with CONV_LOCK:
                CONV_HISTORY[chat_id].append({"role": "assistant", "content": reply})
            return reply
    except Exception as e:
        print(f"主动聊天生成失败: {e}")
    return None


def extract_profile_async(chat_id, user_message, ai_reply):
    if not AI_API_KEY:
        return

    def worker():
        try:
            extract_prompt = f"""你是用户画像分析助手。请从下面这段用户和 AI 的对话中，提取用户的新特征。
只输出 JSON，不要多余文字。格式：
{{"name": null, "traits": [], "preferences": [], "dislikes": [], "recent_mood": null, "notes": []}}
如果没有新信息，全部留空。

用户说：{user_message}
AI 回：{ai_reply}
"""
            resp = requests.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"},
                json={"model": AI_MODEL, "messages": [{"role": "user", "content": extract_prompt}],
                      "temperature": 0.2, "max_tokens": 300},
                timeout=30
            )
            data = resp.json()
            if "choices" not in data or not data["choices"]:
                return
            content = data["choices"][0]["message"]["content"].strip()
            content = re.sub(r'^```json\s*|\s*```$', '', content, flags=re.MULTILINE).strip()
            m = re.search(r'\{.*\}', content, re.DOTALL)
            if not m:
                return
            parsed = json.loads(m.group(0))
            changed = False
            with PROFILE_LOCK:
                if parsed.get("name"):
                    USER_PROFILE["name"] = parsed["name"]
                    changed = True
                for key in ["traits", "preferences", "dislikes", "notes"]:
                    for v in parsed.get(key, []) or []:
                        if v and v not in USER_PROFILE[key]:
                            USER_PROFILE[key].append(v)
                            USER_PROFILE[key] = USER_PROFILE[key][-30:]
                            changed = True
                if parsed.get("recent_mood"):
                    USER_PROFILE["recent_mood"] = parsed["recent_mood"]
                    changed = True
            if changed:
                save_profile()
        except Exception as e:
            print(f"画像提取失败: {e}")

    threading.Thread(target=worker, daemon=True).start()


EMOTIONAL_MESSAGES = [
    "主人，盯盘辛苦啦，喝口水吧！👀", "稳住，别慌，市场永远是对的。🌊",
    "行情总在绝望中诞生，在半信半疑中成长。💡", "亏钱了别难过，被市场毒打是大佬的必经之路。💪",
    "做交易最重要的是活着，还在牌桌上就有机会！🃏", "自律即自由，今天有严格执行计划吗？🎯",
    "浮盈浮亏都是数字，落袋为安才是真金白银。💰", "重仓一时爽，爆仓火葬场。⚖️",
    "一入币圈深似海，记得劳逸结合哦～ 🌴", "不贪不惧，耐心等待属于你的击球点。⚾",
    "交易是一场修行，修的是心。🧘", "主人，不管盈亏，你都是最棒的！⭐",
    "叮！该喝水了主人，身体是革命的本钱！🥤", "频繁操作是亏损的源泉，空仓也是智慧。🛑",
    "止损永远是对的，哪怕事后看是错的。🛡️", "深夜盯盘伤身体，早点休息，明天再战！🌙",
    "主人，空仓、多单还是空单？聊聊呗～ 💬", "别让情绪左右你的交易，冷静，客观。🧊",
    "保持耐心，市场不缺机会，缺的是本金。💎", "交易不是生活的全部，多陪陪家人吧。👨‍👩‍👧",
    "顺势轻仓止损，这六个字值千金。🏆", "横盘最考验耐心，熬过去就是星辰大海。🌌",
    "主人，你已经很优秀了，给自己一点信心！✨", "浮亏加仓是大忌，千万不要逆势抗单！🚫",
    "钱不入急门，慢慢来，比较快。🐢", "今天的持仓，晚上能睡个好觉吗？😴",
    "胜利属于最能忍耐的人，坚持你的系统！💪", "截断亏损，让利润奔跑。🏃‍♂️",
    "主人，无论多疯狂，都要保留一份清醒。🧠", "偶尔离开屏幕，你会发现世界更宽广。🌅",
    "亏损是交易的一部分，接受它，然后放下它。🍃", "别人恐慌的时候，你在做什么？🤔",
    "稳住心态，我们能赢！🏆", "主人，今天也要元气满满哦！☀️"
]
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


def get_updates(offset=None):
    try:
        return requests.get(f"{BASE_URL}/getUpdates", params={"timeout": 30, "offset": offset}, timeout=35).json()
    except Exception as e:
        print("获取更新失败:", e)
        return {}


def send_message(chat_id, text, reply_to_message_id=None):
    global REPLY_TO_MESSAGE_ID
    if reply_to_message_id is None:
        reply_to_message_id = REPLY_TO_MESSAGE_ID
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("发送消息失败:", e)


def get_current_price(symbol):
    inst_id = f"{symbol.upper()}-USDT"
    try:
        resp = requests.get(f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}", timeout=5).json()
        if resp.get("code") == "0" and resp.get("data"):
            return float(resp["data"][0]["last"])
    except Exception:
        pass
    return None


def get_balance_info(chat_id):
    total_pnl = 0.0
    with POS_LOCK:
        ps = list(POSITIONS)
    for pos in ps:
        price = get_current_price(pos["symbol"])
        if price:
            pnl = (price - pos["entry_price"]) * pos["qty"] if pos["side"] == "多" else (pos["entry_price"] - price) * pos["qty"]
            total_pnl += pnl
    msg = f"💰 账户余额\n━━━━━━━━━━━━\n可用资金：{BALANCE:,.2f} USDT\n未实现盈亏：{total_pnl:+,.2f} USDT\n总权益：{BALANCE + total_pnl:,.2f} USDT"
    send_message(chat_id, msg)


def get_position_info(chat_id):
    with POS_LOCK:
        ps = list(POSITIONS)
    if not ps:
        send_message(chat_id, "📭 当前无持仓。空仓也是一种智慧！")
        return
    for pos in ps:
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
        msg = f"📊 {pos['symbol']} 持仓\n━━━━━━━━━━━━\n方向：{pos['side']}\n持仓量：{pos['qty']:.4f}\n开仓价：${pos['entry_price']:,.4f}\n标记价：${price:,.4f}\n爆仓价：${liq_price:,.4f}\n━━━━━━━━━━━━\n保证金：{pos['margin']:,.2f} USDT\n杠杆：{pos['leverage']}x\n收益率：{roe:+.2f}%\n未实现盈亏：{pnl:+,.2f} USDT"
        send_message(chat_id, msg)


def get_trade_history(chat_id):
    with HISTORY_LOCK:
        h = list(TRADE_HISTORY)
    if not h:
        send_message(chat_id, "📭 暂无历史交易记录。")
        return
    total = len(h)
    pnl_sum = sum(t["pnl"] for t in h)
    wins = [t for t in h if t["pnl"] > 0]
    losses = [t for t in h if t["pnl"] <= 0]
    rate = (len(wins) / total * 100) if total else 0
    msg = f"📈 战绩报表\n━━━━━━━━━━━━\n总交易：{total} 次\n总盈亏：{pnl_sum:+,.2f} USDT\n━━━━━━━━━━━━\n胜率：{rate:.2f}%\n盈利：{len(wins)} 次\n亏损：{len(losses)} 次"
    send_message(chat_id, msg)


def open_position(chat_id, symbol, dir_name, leverage, margin):
    global BALANCE
    if margin > BALANCE:
        send_message(chat_id, f"❌ 保证金不足！当前可用：{BALANCE:,.2f} USDT")
        return
    price = get_current_price(symbol)
    if not price:
        send_message(chat_id, f"❌ 无法获取 {symbol} 行情。")
        return
    qty = (margin * leverage) / price
    with POS_LOCK:
        for p in POSITIONS:
            if p["symbol"] == symbol.upper():
                send_message(chat_id, f"⚠️ 已有 {symbol.upper()} 持仓，请先平仓。")
                return
        BALANCE -= margin
        POSITIONS.append({"symbol": symbol.upper(), "side": dir_name, "leverage": leverage,
                          "margin": margin, "entry_price": price, "qty": qty, "chat_id": chat_id,
                          "notified_win": False, "notified_loss": False})
    send_message(chat_id, f"✅ 开仓成功！\n币种：{symbol.upper()}\n方向：{dir_name}\n杠杆：{leverage}x\n保证金：{margin:,.2f} USDT\n开仓价：${price:,.4f}\n数量：{qty:.4f}")


def close_position(chat_id, symbol):
    global BALANCE
    symbol = symbol.upper()
    with POS_LOCK:
        pos = next((p for p in POSITIONS if p["symbol"] == symbol), None)
        if not pos:
            send_message(chat_id, f"📭 未找到 {symbol} 的持仓。")
            return
        price = get_current_price(symbol)
        if not price:
            send_message(chat_id, "❌ 无法获取行情。")
            return
        pnl = (price - pos["entry_price"]) * pos["qty"] if pos["side"] == "多" else (pos["entry_price"] - price) * pos["qty"]
        BALANCE += pos["margin"] + pnl
        POSITIONS.remove(pos)
        with HISTORY_LOCK:
            TRADE_HISTORY.append({"symbol": symbol, "side": pos["side"], "pnl": pnl})
    send_message(chat_id, f"✅ 平仓成功！\n币种：{symbol}\n方向：{pos['side']}\n盈亏：{pnl:+,.2f} USDT\n返还：{pos['margin'] + pnl:,.2f} USDT")


def trigger_liquidation(symbol, price, pos):
    with POS_LOCK:
        if pos in POSITIONS:
            POSITIONS.remove(pos)
    with HISTORY_LOCK:
        TRADE_HISTORY.append({"symbol": symbol, "side": pos["side"], "pnl": -pos["margin"]})
    if not SLEEPING:
        send_message(pos["chat_id"], f"🔔 菜狗你仓位炸了\n币种：{symbol}\n方向：{pos['side']}\n损失保证金：{pos['margin']:,.2f} USDT")


def withdraw_balance(chat_id, amount_str):
    global BALANCE
    try:
        amount = float(amount_str)
    except Exception:
        return
    if amount <= 0 or amount > BALANCE:
        send_message(chat_id, "❌ 提现金额不合法或余额不足！")
        return
    BALANCE -= amount
    send_message(chat_id, f"✅ 提现成功！\n提现：{amount:,.2f} USDT\n当前余额：{BALANCE:,.2f} USDT")


def price_monitor_worker():
    while True:
        try:
            if SLEEPING:
                time.sleep(30)
                continue
            with LST_LOCK:
                cur = list(LST)
            for listener in cur:
                price = get_current_price(listener["symbol"])
                if price is None:
                    continue
                t = listener["target_price"]
                triggered = (t > price and price >= t) or (t <= price and price <= t)
                if triggered:
                    send_message(listener["chat_id"], f"🚨 价格提醒！\n币种：{listener['symbol']}\n当前价：${price:,.4f}")
                    with LST_LOCK:
                        if listener in LST:
                            LST.remove(listener)
        except Exception as e:
            print(f"监听异常: {e}")
        time.sleep(30)


def background_worker(chat_id):
    global LAST_BROADCAST_TIME, LAST_ACTIVITY_TIME, IDLE_NOTIFIED
    print("后台线程已启动...")
    while True:
        try:
            if SLEEPING:
                time.sleep(5)
                continue
            now = time.time()
            with POS_LOCK:
                ps = list(POSITIONS)
            if BROADCAST_ENABLED and (now - LAST_BROADCAST_TIME >= BROADCAST_INTERVAL):
                send_message(chat_id, f"📢 {get_random_message()}")
                LAST_BROADCAST_TIME = now
            with ACTIVITY_LOCK:
                idle = now - LAST_ACTIVITY_TIME
            if ps and idle >= 30 * 60 and not IDLE_NOTIFIED:
                send_message(chat_id, f"⏰ 主人，30分钟没操作啦！{get_random_message()}")
                IDLE_NOTIFIED = True
            for pos in ps:
                price = get_current_price(pos["symbol"])
                if price is None:
                    continue
                if pos["side"] == "多":
                    pnl = (price - pos["entry_price"]) * pos["qty"]
                    liq_price = pos["entry_price"] * (1 - 1 / pos["leverage"])
                else:
                    pnl = (pos["entry_price"] - price) * pos["qty"]
                    liq_price = pos["entry_price"] * (1 + 1 / pos["leverage"])
                roe = (pnl / pos["margin"]) * 100 if pos["margin"] > 0 else 0.0
                if pos["side"] == "多" and price <= liq_price:
                    trigger_liquidation(pos["symbol"], price, pos)
                    continue
                if pos["side"] == "空" and price >= liq_price:
                    trigger_liquidation(pos["symbol"], price, pos)
                    continue
                if roe >= 50 and not pos.get("notified_win"):
                    send_message(pos["chat_id"], "⏰ 主人，盈利 50%+，考虑止盈吗？🚀")
                    with POS_LOCK:
                        if pos in POSITIONS:
                            pos["notified_win"] = True
                if roe <= -50 and not pos.get("notified_loss"):
                    send_message(pos["chat_id"], "⏰ 主人，亏损 50%，注意风险！🩸")
                    with POS_LOCK:
                        if pos in POSITIONS:
                            pos["notified_loss"] = True
        except Exception as e:
            print(f"后台异常: {e}")
        time.sleep(5)


def proactive_chat_worker(chat_id):
    global LAST_PROACTIVE_CHAT_TIME, NEXT_PROACTIVE_INTERVAL
    print("主动聊天线程已启动...")
    while True:
        try:
            now = time.time()
            if SLEEPING:
                time.sleep(60)
                continue
            if now - LAST_PROACTIVE_CHAT_TIME >= NEXT_PROACTIVE_INTERVAL:
                reply = ask_ai_proactive(chat_id)
                if reply:
                    send_message(chat_id, reply)
                LAST_PROACTIVE_CHAT_TIME = now
                NEXT_PROACTIVE_INTERVAL = random.randint(PROACTIVE_CHAT_MIN, PROACTIVE_CHAT_MAX)
                print(f"主动聊天已发送，下次间隔 {NEXT_PROACTIVE_INTERVAL} 秒")
        except Exception as e:
            print(f"主动聊天异常: {e}")
        time.sleep(60)


def handle_message(chat_id, text, message_id=None):
    global BALANCE, LAST_ACTIVITY_TIME, BROADCAST_ENABLED, LAST_BROADCAST_TIME, IDLE_NOTIFIED
    global REPLY_TO_MESSAGE_ID, SLEEPING, SLEEP_START_TIME, LAST_PROACTIVE_CHAT_TIME, NEXT_PROACTIVE_INTERVAL
    REPLY_TO_MESSAGE_ID = message_id
    raw = text.strip()

    now = time.time()
    with ACTIVITY_LOCK:
        idle = now - LAST_ACTIVITY_TIME
        LAST_ACTIVITY_TIME = now
    LAST_PROACTIVE_CHAT_TIME = now
    NEXT_PROACTIVE_INTERVAL = random.randint(PROACTIVE_CHAT_MIN, PROACTIVE_CHAT_MAX)

    if raw == "睡觉":
        SLEEPING = True
        SLEEP_START_TIME = time.time()
        send_message(chat_id, "那本小姐也去休息了。晚安，明早见。🌙")
        return
    if SLEEPING:
        if raw == "早安":
            SLEEPING = False
            duration_hours = (time.time() - SLEEP_START_TIME) / 3600
            complaint = get_wake_message(duration_hours)
            send_message(chat_id, f"{complaint}\n\n早安，笨蛋主人。☀️")
            return
        return

    if idle >= 300:
        send_message(chat_id, "欢迎主人回家🥰")
        IDLE_NOTIFIED = False

    try:
        if raw == "我的画像":
            p = USER_PROFILE
            msg = f"📇 主人画像\n━━━━━━━━━━━━\n"
            msg += f"称呼：{p.get('name', '主人')}\n"
            msg += f"性格/习惯：{', '.join(p.get('traits') or ['暂无'])}\n"
            msg += f"喜欢：{', '.join(p.get('preferences') or ['暂无'])}\n"
            msg += f"不喜欢：{', '.join(p.get('dislikes') or ['暂无'])}\n"
            msg += f"最近情绪：{p.get('recent_mood') or '暂无'}\n"
            msg += f"备注：{', '.join(p.get('notes') or ['暂无'])}"
            send_message(chat_id, msg)
            return

        if raw.startswith("记住"):
            content = raw[2:].strip(" ：:，,")
            if content:
                added = add_to_profile("notes", content)
                send_message(chat_id, "📝 记住了！" if added else "🤔 这个我已经记过啦～")
            return

        if raw == "清空画像":
            with PROFILE_LOCK:
                USER_PROFILE.update({"name": "主人", "traits": [], "preferences": [],
                                     "dislikes": [], "recent_mood": "", "notes": []})
            save_profile()
            send_message(chat_id, "🧹 画像已清空，我们重新认识一下～")
            return

        if raw == "清空对话":
            with CONV_LOCK:
                CONV_HISTORY[chat_id] = []
            send_message(chat_id, "🧹 对话已清空～")
            return

        if raw == "开启播报":
            BROADCAST_ENABLED = True
            LAST_BROADCAST_TIME = time.time()
            send_message(chat_id, "🔊 播报已开启！")
            return
        if raw == "关闭播报":
            BROADCAST_ENABLED = False
            send_message(chat_id, "🔇 播报已关闭。")
            return
        if raw == "安静":
            BROADCAST_ENABLED = False
            send_message(chat_id, "🤫 我安静了。")
            return
        if raw == "正常":
            BROADCAST_ENABLED = True
            LAST_BROADCAST_TIME = time.time()
            send_message(chat_id, "😌 恢复正常模式～")
            return

        if raw.endswith(".") or raw.endswith("。"):
            symbol = raw[:-1].strip().upper()
            if symbol.isalpha() and 2 <= len(symbol) <= 10:
                price = get_current_price(symbol)
                if price:
                    send_message(chat_id, f"📊 {symbol}\n💰 ${price:,.4f}")
            return

        if raw == "myye":
            get_balance_info(chat_id)
            return
        if raw == "战绩":
            get_trade_history(chat_id)
            return
        if raw == "仓位情况":
            get_position_info(chat_id)
            return

        if raw.startswith("监听"):
            m = re.match(r'^监听\s*([a-zA-Z]+)\s*([0-9.]+)$', raw)
            if m:
                sym, tgt = m.group(1).upper(), float(m.group(2))
                with LST_LOCK:
                    LST.append({"symbol": sym, "target_price": tgt, "chat_id": chat_id})
                send_message(chat_id, f"✅ 监听 {sym} @ ${tgt:,.4f}")
            return

        if raw.startswith("充值"):
            m = re.match(r'^充值\s*([0-9.]+)$', raw)
            if m:
                amt = float(m.group(1))
                if amt > 0:
                    BALANCE += amt
                    send_message(chat_id, f"💰 充值成功！余额：{BALANCE:,.2f} USDT")
            return

        if raw.startswith("提现"):
            m = re.match(r'^提现\s*([0-9.]+)$', raw)
            if m:
                withdraw_balance(chat_id, m.group(1))
            return

        if raw.startswith("平仓"):
            m = re.match(r'^平仓\s*([a-zA-Z]+)$', raw)
            if m:
                close_position(chat_id, m.group(1))
            return

        parts = [p for p in raw.replace("，", ",").replace(" ", ",").split(",") if p]
        if len(parts) == 4:
            sym = parts[0].upper()
            lev_str = parts[1].lower().replace("x", "")
            if lev_str.isdigit():
                leverage = int(lev_str)
                if 0 < leverage <= 125:
                    direction = parts[2].lower()
                    dir_name = "多" if direction in ["多", "long", "buy"] else "空" if direction in ["空", "short", "sell"] else None
                    if dir_name:
                        try:
                            margin = float(parts[3])
                            if margin > 0:
                                open_position(chat_id, sym, dir_name, leverage, margin)
                                return
                        except Exception:
                            pass

        if AI_API_KEY:
            if chat_id < 0:
                with GROUP_REPLY_LOCK:
                    cnt = GROUP_REPLY_COUNTER.get(chat_id, 0) + 1
                    if cnt < GROUP_REPLY_INTERVAL:
                        GROUP_REPLY_COUNTER[chat_id] = cnt
                        return
                    else:
                        GROUP_REPLY_COUNTER[chat_id] = 0
            reply = ask_ai(chat_id, raw)
            if reply:
                send_message(chat_id, reply)
                extract_profile_async(chat_id, raw, reply)
            else:
                send_message(chat_id, "🤔 脑子有点卡壳，等会再聊～")
    finally:
        REPLY_TO_MESSAGE_ID = None


def main():
    load_profile()
    if not ALLOWED_USER_ID:
        print("警告：未设置 ALLOWED_USER_ID")
    else:
        print(f"权限控制已开启，只允许 User ID: {ALLOWED_USER_ID}")
    if AI_API_KEY:
        print(f"AI 已启用，模型：{AI_MODEL}")
    else:
        print("⚠️ 未配置 AI_API_KEY，聊天功能关闭")

    t1 = threading.Thread(target=background_worker, args=(ALLOWED_USER_ID,), daemon=True)
    t1.start()
    t2 = threading.Thread(target=price_monitor_worker, daemon=True)
    t2.start()
    t3 = threading.Thread(target=proactive_chat_worker, args=(ALLOWED_USER_ID,), daemon=True)
    t3.start()

    print("Bot 已启动...")
    offset = None
    while True:
        updates = get_updates(offset)
        if "result" in updates:
            for update in updates["result"]:
                offset = update["update_id"] + 1
                msg = update.get("message")
                if not msg:
                    continue
                if ALLOWED_USER_ID and str(msg.get("from", {}).get("id", "")) != ALLOWED_USER_ID:
                    continue
                text = msg.get("text", "")
                if text:
                    handle_message(msg["chat"]["id"], text, msg["message_id"])
        time.sleep(1)


if __name__ == "__main__":
    main()
