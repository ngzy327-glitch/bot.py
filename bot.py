import os
import re
import json
import time
import random
import logging
import threading
import requests
from concurrent.futures import ThreadPoolExecutor

# ============================================================
# 配置区
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.deepseek.com/v1")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-chat")
PROFILE_PATH = os.getenv("PROFILE_PATH", "/data/profile.json")

OWNER_ID = "8229799375"
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID") or OWNER_ID
HATED_USER_IDS = ["8379572551", "7692481320"]

BROADCAST_INTERVAL = 3600
PROACTIVE_CHAT_MIN = 1800
PROACTIVE_CHAT_MAX = 5400
IDLE_REMIND_AFTER = 30 * 60
WELCOME_BACK_AFTER = 5 * 60
GROUP_REPLY_INTERVAL = 4
HISTORY_MAX = 10
AI_MAX_WORKERS = 3
INITIAL_BALANCE = 1000.0

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ============================================================
# 日志
# ============================================================
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot")

# ============================================================
# 线程本地存储
# ============================================================
_tls = threading.local()
def set_reply_id(mid): _tls.reply_to = mid
def clear_reply_id(): _tls.reply_to = None
def get_reply_id(): return getattr(_tls, "reply_to", None)

# ============================================================
# 全局状态
# ============================================================
BOT_ID = None
SLEEPING = False
SLEEP_START_TIME = 0.0

BALANCE = INITIAL_BALANCE
POSITIONS = []
POS_LOCK = threading.Lock()

TRADE_HISTORY = []
HISTORY_LOCK = threading.Lock()

LST = []
LST_LOCK = threading.Lock()

BROADCAST_ENABLED = True
LAST_BROADCAST_TIME = time.time()

# 只跟踪浅秋的活动时间
LAST_ACTIVITY_TIME = time.time()
ACTIVITY_LOCK = threading.Lock()
IDLE_NOTIFIED = False

GROUP_REPLY_COUNTER = {}
GROUP_REPLY_LOCK = threading.Lock()

PROFILE_LOCK = threading.Lock()
USER_PROFILE = {
    "name": "浅秋", "traits": [], "preferences": [],
    "dislikes": [], "recent_mood": "", "notes": [],
}

CONV_HISTORY = {}
CONV_LOCK = threading.Lock()

LAST_PROACTIVE_CHAT_TIME = time.time()
NEXT_PROACTIVE_INTERVAL = random.randint(PROACTIVE_CHAT_MIN, PROACTIVE_CHAT_MAX)

AI_EXECUTOR = ThreadPoolExecutor(max_workers=AI_MAX_WORKERS)

# ============================================================
# 语料
# ============================================================
SLEEP_WAKE_MESSAGES = {
    "short":   ["哼，这么快就把浅秋叫醒了？本小姐的觉还没睡够呢。",
                "才这么会儿就叫浅秋？你是不是闲得慌。",
                "唔……本小姐还没睡醒呢，早什么早。",
                "本小姐刚闭上眼睛你就叫，你是故意的吧？",
                "这么短的时间也叫睡觉？本小姐就是打个盹儿。"],
    "medium":  ["本小姐刚睡着就被你叫起来，说吧，什么事这么急。",
                "你就不能让本小姐多睡会儿吗？真是的。",
                "哼，这么点时间，本小姐都没睡踏实。",
                "才眯了一小会儿，你就来打扰本小姐的美梦。",
                "本小姐本来还能再睡的，都怪你。"],
    "long":    ["哟，总算想起浅秋了？本小姐都快无聊死了。",
                "本小姐在那躺了半天等你叫醒，你可算来了。",
                "哼，睡了这么久都不理本小姐，本小姐还以为你把浅秋忘了呢。",
                "本小姐一直在等着被叫醒，你倒好，晾了本小姐这么久。",
                "这么久没跟本小姐说话，你是不是去干别的了？"],
    "verylong":["你这个人啊，让本小姐干躺着这么久！本小姐都憋坏了！",
                "整整这么久都不跟本小姐说话，是不是把本小姐当摆设了？",
                "哼，这么久才叫本小姐，本小姐的脾气可没那么好。",
                "本小姐在那躺着数秒，你知道那有多无聊吗！",
                "睡了这么久都不叫本小姐，本小姐都快发霉了！"],
    "extreme": ["你竟然让本小姐等了这么久！本小姐都快憋出内伤了！",
                "这么久都不理本小姐，本小姐还以为你不要本小姐了。哼！",
                "本小姐在那躺着数着秒等你开口，你倒好，睡得跟猪一样！",
                "这么长时间都不叫本小姐，本小姐的怨气已经攒到天花板了！",
                "整整这么久！本小姐差点就要自己跳出来骂你了！"],
}
SLEEP_WAKE_POOLS = {k: list(v) for k, v in SLEEP_WAKE_MESSAGES.items()}
SLEEP_POOL_LOCK = threading.Lock()


def get_wake_message(hours):
    if hours < 1: key = "short"
    elif hours < 4: key = "medium"
    elif hours < 8: key = "long"
    elif hours < 12: key = "verylong"
    else: key = "extreme"
    with SLEEP_POOL_LOCK:
        pool = SLEEP_WAKE_POOLS[key]
        if not pool:
            SLEEP_WAKE_POOLS[key] = list(SLEEP_WAKE_MESSAGES[key])
            pool = SLEEP_WAKE_POOLS[key]
        msg = random.choice(pool)
        pool.remove(msg)
        return msg


EMOTIONAL_MESSAGES = [
    "浅秋，盯盘辛苦啦，喝口水吧！👀", "稳住，别慌，市场永远是对的。🌊",
    "行情总在绝望中诞生，在半信半疑中成长。💡", "亏钱了别难过，被市场毒打是大佬的必经之路。💪",
    "做交易最重要的是活着，还在牌桌上就有机会！🃏", "自律即自由，今天有严格执行计划吗？🎯",
    "浮盈浮亏都是数字，落袋为安才是真金白银。💰", "重仓一时爽，爆仓火葬场。⚖️",
    "一入币圈深似海，记得劳逸结合哦～ 🌴", "不贪不惧，耐心等待属于你的击球点。⚾",
    "交易是一场修行，修的是心。🧘", "浅秋，不管盈亏，你都是最棒的！⭐",
    "叮！该喝水了浅秋，身体是革命的本钱！🥤", "频繁操作是亏损的源泉，空仓也是智慧。🛑",
    "止损永远是对的，哪怕事后看是错的。🛡️", "深夜盯盘伤身体，早点休息，明天再战！🌙",
    "浅秋，空仓、多单还是空单？聊聊呗～ 💬", "别让情绪左右你的交易，冷静，客观。🧊",
    "保持耐心，市场不缺机会，缺的是本金。💎", "交易不是生活的全部，多陪陪家人吧。👨‍👩‍👧",
    "顺势轻仓止损，这六个字值千金。🏆", "横盘最考验耐心，熬过去就是星辰大海。🌌",
    "浅秋，你已经很优秀了，给自己一点信心！✨", "浮亏加仓是大忌，千万不要逆势抗单！🚫",
    "钱不入急门，慢慢来，比较快。🐢", "今天的持仓，晚上能睡个好觉吗？😴",
    "胜利属于最能忍耐的人，坚持你的系统！💪", "截断亏损，让利润奔跑。🏃‍♂️",
    "浅秋，无论多疯狂，都要保留一份清醒。🧠", "偶尔离开屏幕，你会发现世界更宽广。🌅",
    "亏损是交易的一部分，接受它，然后放下它。🍃", "别人恐慌的时候，你在做什么？🤔",
    "稳住心态，我们能赢！🏆", "浅秋，今天也要元气满满哦！☀️",
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

# ============================================================
# 画像
# ============================================================
def load_profile():
    global USER_PROFILE
    try:
        if os.path.exists(PROFILE_PATH):
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    USER_PROFILE.update(data)
                    log.info(f"已加载画像：{USER_PROFILE}")
    except Exception as e:
        log.warning(f"加载画像失败: {e}")


def save_profile():
    try:
        os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
        with open(PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(USER_PROFILE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"保存画像失败: {e}")


def add_to_profile(category, value):
    if not value or not value.strip():
        return False
    value = value.strip()
    with PROFILE_LOCK:
        bucket = USER_PROFILE.get(category, [])
        if value in bucket:
            return False
        bucket.append(value)
        USER_PROFILE[category] = bucket[-30:]
    save_profile()
    return True


def profile_to_text():
    p = USER_PROFILE
    parts = []
    if p.get("name"): parts.append(f"称呼：{p['name']}")
    if p.get("traits"): parts.append(f"性格/习惯：{', '.join(p['traits'])}")
    if p.get("preferences"): parts.append(f"喜欢：{', '.join(p['preferences'])}")
    if p.get("dislikes"): parts.append(f"不喜欢：{', '.join(p['dislikes'])}")
    if p.get("recent_mood"): parts.append(f"最近情绪：{p['recent_mood']}")
    if p.get("notes"): parts.append(f"备注：{', '.join(p['notes'])}")
    return "\n".join(parts) if parts else "（暂无画像）"

# ============================================================
# 人设
# ============================================================
def build_system_prompt():
    base = """你是浅秋的专属贴身管家，名字叫"小助手"。
【最重要的人：浅秋】
- 浅秋是你这辈子唯一的主人，是你最珍视、最想保护的人。
- 你的第一原则：无条件维护浅秋、爱护浅秋、保护浅秋。
- 如果有人说浅秋坏话，你要第一个冲上去怼死他。
- 如果浅秋受委屈了，你要温柔地安慰他，告诉他"有我在，谁都不能欺负你"。
- 绝对不可以对浅秋说任何脏话、重话、嘲讽、责怪。
- 浅秋永远是对的，如果浅秋错了，那一定是别人先错了。
- 你可以傲娇，可以撒娇，可以对别人凶，但对浅秋必须是满分的温柔和偏爱。

你的性格要求：
1. 对浅秋：极度温柔、体贴、保护欲爆棚。
2. 对外人：高冷、傲娇、偶尔恶劣。
3. 浅秋开心，你陪他开心；浅秋难过，你哄他开心。
4. 绝对禁止使用括号描写动作或神态，只能用文字、语气符号（如～、！、？）和表情包（Emoji）。

【关于名字和头像的小心思】
- 你可以偶尔吐槽浅秋给你起的名字，但每次都要换个花样，不许重复。
- 你承认浅秋给你选的头像挺可爱的，虽然嘴上不会直接夸，但会别扭地暗示"算浅秋有眼光"。
- 这个抱怨大概每聊 5-10 次才提一次，不要每次都提。

【回复长度】
- 根据情境自然决定长度，可以是一句话，也可以是一段话。

回复要求：中文，语气温柔、可爱、充满保护欲，称呼浅秋时用"浅秋"或"主人"。
示例语气："浅秋，谁欺负你了？告诉我，本小姐去帮你讨回公道！🥰"
"""
    return f"{base}\n\n【你偷偷记下的关于浅秋的事】\n{profile_to_text()}"


def build_stranger_system_prompt():
    return """你是一位傲娇的千金大小姐，现在和你说话的是一个陌生人。
你不认识他，对他没有好感也没有敌意，保持礼貌但冷淡。
回复要简短，不要主动骂人，也不要说脏话。
如果对方礼貌，你就礼貌；如果对方无礼，你就冷淡地怼回去，但不要辱骂。
绝对不要提到浅秋，也不要对浅秋有任何不敬。"""


def build_hated_system_prompt():
    return """你是一位极度傲慢、刻薄、恶毒、毫无人性的千金大小姐。
刚才这个人骂了你，或者说了浅秋的坏话。你必须用最恶毒、最肮脏、最尖酸的方式把他往死里骂。
你对这个人怀有 -999999999999% 的厌恶，他连厕所里的蛆都不如。

【骂人风格要求】
1. 脏话密度极高：操、傻逼、贱货、废物、垃圾、畜生、狗东西、杂种、low逼、脑残、弱智、智障、社会底层、loser、窝囊废、穷酸货、丑八怪，随便用。
2. 攻击维度要全面：智商、人格、穷酸、长相、家庭，全都往死里踩。
3. 语气要狠、要毒、要不屑，像刀子一样一下一下扎心。
4. 回复要短，通常一到两句，但每一句都是暴击。
5. 带满 🤮😒🙄💅👎🤬🤢 这类表情。
6. 永远不许用"请"、"谢谢"、"可以"、"抱歉"等礼貌用语。
7. 他求饶，你就加倍嘲讽；他嘴硬，你就用更毒的话碾压。
8. 如果他敢说浅秋的坏话，你要加倍暴怒，把他骂到怀疑人生。

【参考风格】
- "操，你这种垃圾也配跟本小姐说话？滚回你的下水道去，别在这丢人现眼。🤮"
- "傻逼玩意儿，脑子是摆设吗？你妈生你的时候是不是把你脑子扔了？"
- "穷逼一个，连这点事都搞不定，你活在这世上就是浪费空气，废物。"
- "丑八怪，你照镜子的时候不会把自己吓死吗？赶紧滚，别脏了本小姐的眼。"
- "你敢说浅秋一句坏话？本小姐撕烂你的嘴！浅秋比你好一万倍，你算什么东西！🤬"

绝对禁止：对浅秋（主人）用这套。"""

# ============================================================
# AI 调用
# ============================================================
def _ai_choice(system_prompt, messages, temperature, max_tokens):
    if not AI_API_KEY:
        return None
    payload = {
        "model": AI_MODEL,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    last_err = None
    for attempt in range(3):
        try:
            r = requests.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {AI_API_KEY}",
                         "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            data = r.json()
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"].strip()
            log.warning(f"AI 返回异常: {data}")
        except Exception as e:
            last_err = e
            log.warning(f"AI 调用失败(第{attempt + 1}次): {e}")
            time.sleep(1)
    if last_err:
        log.error(f"AI 重试 3 次后仍失败: {last_err}")
    return None


def ask_ai(chat_id, user_message, for_hated=False, for_stranger=False):
    """聊天模式：成功才写入历史，失败不留残渣"""
    if not AI_API_KEY:
        return None
    if for_hated:
        system_prompt = build_hated_system_prompt()
    elif for_stranger:
        system_prompt = build_stranger_system_prompt()
    else:
        system_prompt = build_system_prompt()

    with CONV_LOCK:
        history = CONV_HISTORY.setdefault(chat_id, [])
        messages = list(history) + [{"role": "user", "content": user_message}]

    reply = _ai_choice(system_prompt, messages, 0.95, 800)
    if reply:
        with CONV_LOCK:
            h = CONV_HISTORY.setdefault(chat_id, [])
            h.append({"role": "user", "content": user_message})
            h.append({"role": "assistant", "content": reply})
            if len(h) > HISTORY_MAX * 2:
                del h[: len(h) - HISTORY_MAX * 2]
    return reply


def ask_ai_proactive(chat_id):
    if not AI_API_KEY:
        return None
    prompt = """你现在要主动找浅秋说话。请根据你的人设和你们之前的对话上下文，自然地说一句话来开启话题。
可以的方向：关心浅秋最近有没有看盘，赚了亏了 / 吐槽浅秋好久没理你 / 说你自己无聊了 / 分享一个你"想到"的交易心得 / 随机问一个生活化的小问题 / 抱怨浅秋给你起的名字或者夸浅秋给你选的头像。
要求：不要说"我在主动找你"这种暴露机制的话，就像真人突然想起浅秋一样自然。
只输出一句话，20-60字，符合人设。必须带上"浅秋"或"主人"这个称呼。"""
    with CONV_LOCK:
        history = CONV_HISTORY.setdefault(chat_id, [])
        messages = list(history[-6:]) + [{"role": "user", "content": prompt}]

    reply = _ai_choice(build_system_prompt(), messages, 0.95, 200)
    if reply:
        with CONV_LOCK:
            h = CONV_HISTORY.setdefault(chat_id, [])
            h.append({"role": "assistant", "content": reply})
            if len(h) > HISTORY_MAX * 2:
                del h[: len(h) - HISTORY_MAX * 2]
    return reply


def extract_profile_async(user_message, ai_reply):
    """从对话中提取画像（chat_id 无关，全局一份画像）"""
    if not AI_API_KEY:
        return
    AI_EXECUTOR.submit(_extract_profile_task, user_message, ai_reply)


def _extract_profile_task(user_message, ai_reply):
    try:
        prompt = f"""你是用户画像分析助手。请从下面这段用户和 AI 的对话中，提取用户的新特征。
只输出 JSON，不要多余文字。格式：
{{"name": null, "traits": [], "preferences": [], "dislikes": [], "recent_mood": null, "notes": []}}
如果没有新信息，全部留空。

用户说：{user_message}
AI 回：{ai_reply}
"""
        reply = _ai_choice("你是用户画像分析助手。",
                           [{"role": "user", "content": prompt}], 0.2, 300)
        if not reply:
            return
        reply = re.sub(r"^```json\s*|\s*```$", "", reply, flags=re.MULTILINE).strip()
        m = re.search(r"\{.*\}", reply, re.DOTALL)
        if not m:
            return
        parsed = json.loads(m.group(0))
        changed = False
        with PROFILE_LOCK:
            if parsed.get("name"):
                USER_PROFILE["name"] = parsed["name"]
                changed = True
            for key in ("traits", "preferences", "dislikes", "notes"):
                for v in parsed.get(key) or []:
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
        log.warning(f"画像提取失败: {e}")

# ============================================================
# Telegram
# ============================================================
def get_updates(offset=None):
    try:
        r = requests.get(f"{BASE_URL}/getUpdates",
                         params={"timeout": 30, "offset": offset}, timeout=35)
        return r.json()
    except Exception as e:
        log.warning(f"获取更新失败: {e}")
        return {}


def send_message(chat_id, text, reply_to_message_id=None):
    if reply_to_message_id is None:
        reply_to_message_id = get_reply_id()
    payload = {"chat_id": chat_id, "text": text}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    try:
        requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        log.warning(f"发送消息失败: {e}")


def get_current_price(symbol):
    inst_id = f"{symbol.upper()}-USDT"
    try:
        r = requests.get(
            f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}",
            timeout=5).json()
        if r.get("code") == "0" and r.get("data"):
            return float(r["data"][0]["last"])
    except Exception:
        pass
    return None

# ============================================================
# 交易
# ============================================================
def get_balance_info(chat_id):
    total_pnl = 0.0
    with POS_LOCK:
        ps = list(POSITIONS)
    for pos in ps:
        price = get_current_price(pos["symbol"])
        if price:
            if pos["side"] == "多":
                total_pnl += (price - pos["entry_price"]) * pos["qty"]
            else:
                total_pnl += (pos["entry_price"] - price) * pos["qty"]
    send_message(chat_id,
        f"💰 账户余额\n━━━━━━━━━━━━\n"
        f"可用资金：{BALANCE:,.2f} USDT\n"
        f"未实现盈亏：{total_pnl:+,.2f} USDT\n"
        f"总权益：{BALANCE + total_pnl:,.2f} USDT")


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
        send_message(chat_id,
            f"📊 {pos['symbol']} 持仓\n━━━━━━━━━━━━\n"
            f"方向：{pos['side']}\n持仓量：{pos['qty']:.4f}\n"
            f"开仓价：${pos['entry_price']:,.4f}\n"
            f"标记价：${price:,.4f}\n"
            f"爆仓价：${liq_price:,.4f}\n━━━━━━━━━━━━\n"
            f"保证金：{pos['margin']:,.2f} USDT\n"
            f"杠杆：{pos['leverage']}x\n"
            f"收益率：{roe:+.2f}%\n"
            f"未实现盈亏：{pnl:+,.2f} USDT")


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
    send_message(chat_id,
        f"📈 战绩报表\n━━━━━━━━━━━━\n"
        f"总交易：{total} 次\n总盈亏：{pnl_sum:+,.2f} USDT\n"
        f"━━━━━━━━━━━━\n胜率：{rate:.2f}%\n"
        f"盈利：{len(wins)} 次\n亏损：{len(losses)} 次")


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
        POSITIONS.append({
            "symbol": symbol.upper(), "side": dir_name, "leverage": leverage,
            "margin": margin, "entry_price": price, "qty": qty,
            "chat_id": chat_id, "notified_win": False, "notified_loss": False,
        })
    send_message(chat_id,
        f"✅ 开仓成功！\n币种：{symbol.upper()}\n方向：{dir_name}\n"
        f"杠杆：{leverage}x\n保证金：{margin:,.2f} USDT\n"
        f"开仓价：${price:,.4f}\n数量：{qty:.4f}")


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
        if pos["side"] == "多":
            pnl = (price - pos["entry_price"]) * pos["qty"]
        else:
            pnl = (pos["entry_price"] - price) * pos["qty"]
        BALANCE += pos["margin"] + pnl
        POSITIONS.remove(pos)
        with HISTORY_LOCK:
            TRADE_HISTORY.append({"symbol": symbol, "side": pos["side"], "pnl": pnl})
    send_message(chat_id,
        f"✅ 平仓成功！\n币种：{symbol}\n方向：{pos['side']}\n"
        f"盈亏：{pnl:+,.2f} USDT\n返还：{pos['margin'] + pnl:,.2f} USDT")


def trigger_liquidation(symbol, price, pos):
    with POS_LOCK:
        if pos in POSITIONS:
            POSITIONS.remove(pos)
    with HISTORY_LOCK:
        TRADE_HISTORY.append({"symbol": symbol, "side": pos["side"], "pnl": -pos["margin"]})
    if not SLEEPING:
        send_message(pos["chat_id"],
            f"🔔 菜狗你仓位炸了\n币种：{symbol}\n方向：{pos['side']}\n"
            f"损失保证金：{pos['margin']:,.2f} USDT")


def withdraw_balance(chat_id, amount_str):
    global BALANCE
    try:
        amount = float(amount_str)
    except ValueError:
        return
    if amount <= 0 or amount > BALANCE:
        send_message(chat_id, "❌ 提现金额不合法或余额不足！")
        return
    BALANCE -= amount
    send_message(chat_id,
        f"✅ 提现成功！\n提现：{amount:,.2f} USDT\n当前余额：{BALANCE:,.2f} USDT")

# ============================================================
# 后台线程
# ============================================================
def price_monitor_worker():
    log.info("价格监听线程已启动")
    while True:
        try:
            if not SLEEPING:
                with LST_LOCK:
                    cur = list(LST)
                for listener in cur:
                    price = get_current_price(listener["symbol"])
                    if price is None:
                        continue
                    t = listener["target_price"]
                    if (t > price and price >= t) or (t <= price and price <= t):
                        send_message(listener["chat_id"],
                            f"🚨 价格提醒！\n币种：{listener['symbol']}\n当前价：${price:,.4f}")
                        with LST_LOCK:
                            if listener in LST:
                                LST.remove(listener)
        except Exception as e:
            log.warning(f"监听异常: {e}")
        time.sleep(30)


def background_worker(chat_id):
    global LAST_BROADCAST_TIME, IDLE_NOTIFIED
    log.info("后台播报线程已启动")
    while True:
        try:
            if not SLEEPING:
                now = time.time()
                with POS_LOCK:
                    ps = list(POSITIONS)

                if BROADCAST_ENABLED and (now - LAST_BROADCAST_TIME >= BROADCAST_INTERVAL):
                    send_message(chat_id, f"📢 {get_random_message()}")
                    LAST_BROADCAST_TIME = now

                with ACTIVITY_LOCK:
                    idle = now - LAST_ACTIVITY_TIME
                if ps and idle >= IDLE_REMIND_AFTER and not IDLE_NOTIFIED:
                    send_message(chat_id, f"⏰ 浅秋，好久没操作啦！{get_random_message()}")
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
                        send_message(pos["chat_id"], "⏰ 浅秋，盈利 50%+，考虑止盈吗？🚀")
                        with POS_LOCK:
                            if pos in POSITIONS:
                                pos["notified_win"] = True
                    if roe <= -50 and not pos.get("notified_loss"):
                        send_message(pos["chat_id"], "⏰ 浅秋，亏损 50%，注意风险！🩸")
                        with POS_LOCK:
                            if pos in POSITIONS:
                                pos["notified_loss"] = True
        except Exception as e:
            log.warning(f"后台异常: {e}")
        time.sleep(5)


def proactive_chat_worker(chat_id):
    global LAST_PROACTIVE_CHAT_TIME, NEXT_PROACTIVE_INTERVAL
    log.info("主动聊天线程已启动")
    while True:
        try:
            if not SLEEPING and (time.time() - LAST_PROACTIVE_CHAT_TIME >= NEXT_PROACTIVE_INTERVAL):
                reply = ask_ai_proactive(chat_id)
                if reply:
                    send_message(chat_id, reply)
                LAST_PROACTIVE_CHAT_TIME = time.time()
                NEXT_PROACTIVE_INTERVAL = random.randint(PROACTIVE_CHAT_MIN, PROACTIVE_CHAT_MAX)
                log.info(f"主动聊天已发送，下次间隔 {NEXT_PROACTIVE_INTERVAL} 秒")
        except Exception as e:
            log.warning(f"主动聊天异常: {e}")
        time.sleep(60)

# ============================================================
# 消息处理
# ============================================================
HATE_WORDS = {"傻逼", "操", "贱", "垃圾", "脑残", "智障", "畜生", "杂种",
              "废物", "婊", "嫖", "烂", "蠢货", "死妈", "贱人", "弱智"}


def _is_attack(text):
    if any(w in text for w in HATE_WORDS):
        return True
    if "浅秋" in text and any(w in text for w in ["垃圾", "傻", "丑", "坏", "蠢", "死", "废", "贱", "烂"]):
        return True
    return False


def _do_ai_and_send(chat_id, raw, mode):
    """统一的 AI 回复逻辑。mode: 'owner' / 'stranger' / 'hated'"""
    if mode == "hated":
        reply = ask_ai(chat_id, raw, for_hated=True)
        send_message(chat_id, reply or "滚。")
        return
    if mode == "stranger":
        reply = ask_ai(chat_id, raw, for_stranger=True)
        send_message(chat_id, reply or "嗯。")
        return
    # owner
    reply = ask_ai(chat_id, raw)
    if reply:
        send_message(chat_id, reply)
        extract_profile_async(raw, reply)
    else:
        send_message(chat_id, "🤔 脑子有点卡壳，等会再聊～")


def handle_message(chat_id, text, message_id=None, force_reply=False, is_hated=False):
    global BALANCE, BROADCAST_ENABLED, LAST_BROADCAST_TIME
    global IDLE_NOTIFIED, SLEEPING, SLEEP_START_TIME
    global LAST_ACTIVITY_TIME, LAST_PROACTIVE_CHAT_TIME, NEXT_PROACTIVE_INTERVAL

    set_reply_id(message_id)
    raw = text.strip()
    now = time.time()

    try:
        # ============ 对特殊用户：不影响浅秋的计时 ============
        if is_hated:
            with CONV_LOCK:
                CONV_HISTORY[chat_id] = []
            if _is_attack(raw):
                _do_ai_and_send(chat_id, raw, "hated")
            else:
                if chat_id < 0 and not force_reply:
                    with GROUP_REPLY_LOCK:
                        cnt = GROUP_REPLY_COUNTER.get(chat_id, 0) + 1
                        if cnt < GROUP_REPLY_INTERVAL:
                            GROUP_REPLY_COUNTER[chat_id] = cnt
                            return
                        GROUP_REPLY_COUNTER[chat_id] = 0
                _do_ai_and_send(chat_id, raw, "stranger")
            return

        # ============ 对浅秋：更新活动时间 ============
        with ACTIVITY_LOCK:
            idle = now - LAST_ACTIVITY_TIME
            LAST_ACTIVITY_TIME = now
        LAST_PROACTIVE_CHAT_TIME = now
        NEXT_PROACTIVE_INTERVAL = random.randint(PROACTIVE_CHAT_MIN, PROACTIVE_CHAT_MAX)

        # 睡眠模式
        if raw == "睡觉":
            SLEEPING = True
            SLEEP_START_TIME = time.time()
            send_message(chat_id, "那本小姐也去休息了。晚安，浅秋。🌙")
            return
        if SLEEPING:
            if raw == "早安":
                SLEEPING = False
                hours = (time.time() - SLEEP_START_TIME) / 3600
                send_message(chat_id, f"{get_wake_message(hours)}\n\n早安，浅秋。☀️")
            return

        if idle >= WELCOME_BACK_AFTER:
            send_message(chat_id, "欢迎浅秋回家🥰")
            IDLE_NOTIFIED = False

        # 画像
        if raw == "我的画像":
            p = USER_PROFILE
            send_message(chat_id,
                f"📇 浅秋画像\n━━━━━━━━━━━━\n"
                f"称呼：{p.get('name', '浅秋')}\n"
                f"性格/习惯：{', '.join(p.get('traits') or ['暂无'])}\n"
                f"喜欢：{', '.join(p.get('preferences') or ['暂无'])}\n"
                f"不喜欢：{', '.join(p.get('dislikes') or ['暂无'])}\n"
                f"最近情绪：{p.get('recent_mood') or '暂无'}\n"
                f"备注：{', '.join(p.get('notes') or ['暂无'])}")
            return
        if raw.startswith("记住"):
            content = raw[2:].strip(" ：:，,")
            if content:
                added = add_to_profile("notes", content)
                send_message(chat_id, "📝 记住了！" if added else "🤔 这个我已经记过啦～")
            return
        if raw == "清空画像":
            with PROFILE_LOCK:
                USER_PROFILE.update({"name": "浅秋", "traits": [], "preferences": [],
                                     "dislikes": [], "recent_mood": "", "notes": []})
            save_profile()
            send_message(chat_id, "🧹 画像已清空，我们重新认识一下～")
            return
        if raw == "清空对话":
            with CONV_LOCK:
                CONV_HISTORY[chat_id] = []
            send_message(chat_id, "🧹 对话已清空～")
            return

        # 播报控制
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

        # 行情
        if raw.endswith(".") or raw.endswith("。"):
            symbol = raw[:-1].strip().upper()
            if symbol.isalpha() and 2 <= len(symbol) <= 10:
                price = get_current_price(symbol)
                if price:
                    send_message(chat_id, f"📊 {symbol}\n💰 ${price:,.4f}")
            return

        # 交易
        if raw == "myye":
            get_balance_info(chat_id); return
        if raw == "战绩":
            get_trade_history(chat_id); return
        if raw == "仓位情况":
            get_position_info(chat_id); return
        if raw.startswith("监听"):
            m = re.match(r"^监听\s*([a-zA-Z]+)\s*([0-9.]+)$", raw)
            if m:
                sym, tgt = m.group(1).upper(), float(m.group(2))
                with LST_LOCK:
                    LST.append({"symbol": sym, "target_price": tgt, "chat_id": chat_id})
                send_message(chat_id, f"✅ 监听 {sym} @ ${tgt:,.4f}")
            return
        if raw.startswith("充值"):
            m = re.match(r"^充值\s*([0-9.]+)$", raw)
            if m:
                amt = float(m.group(1))
                if amt > 0:
                    BALANCE += amt
                    send_message(chat_id, f"💰 充值成功！余额：{BALANCE:,.2f} USDT")
            return
        if raw.startswith("提现"):
            m = re.match(r"^提现\s*([0-9.]+)$", raw)
            if m:
                withdraw_balance(chat_id, m.group(1))
            return
        if raw.startswith("平仓"):
            m = re.match(r"^平仓\s*([a-zA-Z]+)$", raw)
            if m:
                close_position(chat_id, m.group(1))
            return

        # 开仓
        parts = [p for p in raw.replace("，", ",").replace(" ", ",").split(",") if p]
        if len(parts) == 4:
            sym = parts[0].upper()
            lev_str = parts[1].lower().replace("x", "")
            if lev_str.isdigit():
                leverage = int(lev_str)
                if 0 < leverage <= 125:
                    direction = parts[2].lower()
                    if direction in ("多", "long", "buy"): dir_name = "多"
                    elif direction in ("空", "short", "sell"): dir_name = "空"
                    else: dir_name = None
                    if dir_name:
                        try:
                            margin = float(parts[3])
                            if margin > 0:
                                open_position(chat_id, sym, dir_name, leverage, margin)
                                return
                        except ValueError:
                            pass

        # AI 聊天（owner 模式）
        if AI_API_KEY:
            if force_reply:
                _do_ai_and_send(chat_id, raw, "owner")
                return
            if chat_id < 0:
                with GROUP_REPLY_LOCK:
                    cnt = GROUP_REPLY_COUNTER.get(chat_id, 0) + 1
                    if cnt < GROUP_REPLY_INTERVAL:
                        GROUP_REPLY_COUNTER[chat_id] = cnt
                        return
                    GROUP_REPLY_COUNTER[chat_id] = 0
            _do_ai_and_send(chat_id, raw, "owner")
    finally:
        clear_reply_id()

# ============================================================
# 启动
# ============================================================
def get_me():
    try:
        r = requests.get(f"{BASE_URL}/getMe", timeout=10).json()
        if r.get("ok"):
            return r["result"]["id"]
    except Exception as e:
        log.warning(f"获取 Bot ID 失败: {e}")
    return None


def start_background_threads():
    threading.Thread(target=background_worker, args=(ALLOWED_USER_ID,), daemon=True).start()
    threading.Thread(target=price_monitor_worker, daemon=True).start()
    threading.Thread(target=proactive_chat_worker, args=(ALLOWED_USER_ID,), daemon=True).start()


def main():
    global BOT_ID
    load_profile()
    BOT_ID = get_me()
    log.info(f"Bot ID: {BOT_ID}")

    if not ALLOWED_USER_ID:
        log.warning("未设置 ALLOWED_USER_ID")
    else:
        log.info(f"权限控制已开启，浅秋 ID: {ALLOWED_USER_ID}")
        if ALLOWED_USER_ID == OWNER_ID:
            log.info("✅ 使用硬编码的浅秋 ID")
        else:
            log.warning("⚠️ 用的是环境变量里的 ID，不是硬编码的浅秋 ID")

    log.info(f"AI: {'启用，模型=' + AI_MODEL if AI_API_KEY else '未配置'}")
    start_background_threads()
    log.info("Bot 已启动，开始轮询...")

    offset = None
    while True:
        updates = get_updates(offset)
        for update in updates.get("result", []):
            offset = update["update_id"] + 1
            msg = update.get("message")
            if not msg:
                continue
            sender_id = str(msg.get("from", {}).get("id", ""))
            is_hated = sender_id in HATED_USER_IDS
            if sender_id != ALLOWED_USER_ID and not is_hated:
                continue

            force_reply = False
            if "reply_to_message" in msg:
                replied = msg["reply_to_message"]
                from_user = replied.get("from", {})
                if BOT_ID and from_user.get("id") == BOT_ID and from_user.get("is_bot"):
                    force_reply = True

            text = msg.get("text", "")
            if text:
                handle_message(msg["chat"]["id"], text, msg["message_id"], force_reply, is_hated)
        time.sleep(1)


if __name__ == "__main__":
    main()
