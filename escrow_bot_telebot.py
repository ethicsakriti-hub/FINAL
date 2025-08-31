import telebot
import time
from collections import defaultdict

# === CONFIG ===
TOKEN = "YOUR_BOT_TOKEN"   # BotFather token
target_channel = "@your_channel"  # logs channel
OWNER_ID = 123456789  # your Telegram ID

bot = telebot.TeleBot(TOKEN)

# === DATA STORAGE ===
admins = [OWNER_ID]
trade_id = 1
trades = {}  # {tid: {buyer, seller, amount, status, chat_id, admin}}

# === GLOBAL STATS TRACKER ===
stats_24h = defaultdict(lambda: {"completed": 0, "refunded": 0, "trades": 0, "volume": 0.0})
last_reset = time.time()

# === HELPERS ===
def is_admin(user_id):
    return user_id in admins or user_id == OWNER_ID

def calc_fee(amount):
    fee = round(float(amount) * 0.03, 2)
    total = round(float(amount) + fee, 2)
    return fee, total

def extract_form(text):
    lines = text.splitlines()
    buyer = seller = None
    amount = None
    for line in lines:
        if line.startswith("BUYER"):
            buyer = line.split(":")[1].strip()
        elif line.startswith("SELLER"):
            seller = line.split(":")[1].strip()
        elif line.startswith("DEAL AMOUNT"):
            try:
                amount = float(line.split(":")[1].strip().replace("₹",""))
            except:
                pass
    return buyer, seller, amount

def reset_stats():
    global stats_24h, last_reset
    now = time.time()
    if now - last_reset >= 86400:  # 24h
        stats_24h = defaultdict(lambda: {"completed": 0, "refunded": 0, "trades": 0, "volume": 0.0})
        last_reset = now

def update_stats(admin, event, amount):
    reset_stats()
    stats_24h[admin]["trades"] += 1
    stats_24h[admin]["volume"] += amount
    if event == "completed":
        stats_24h[admin]["completed"] += amount
    elif event == "refunded":
        stats_24h[admin]["refunded"] += amount

def get_hold(admin=None):
    if admin:
        return sum(t["amount"] for t in trades.values() if t["status"] == "open" and t["admin"] == admin)
    return sum(t["amount"] for t in trades.values() if t["status"] == "open")

# === START ===
@bot.message_handler(commands=["start"])
def start(msg):
    bot.reply_to(msg,
        "👋 Welcome to Escrow Bot!\n"
        "1️⃣ Post manual deal form:\n"
        "   BUYER : @buyer\n"
        "   SELLER : @seller\n"
        "   DEAL AMOUNT : 100\n"
        "   DEAL INFO : test\n"
        "   TIME TO DEAL : 10min\n\n"
        "2️⃣ Admin replies with /add or /add+fee\n"
        "3️⃣ Later use /done, /done+fee, /refund, /refund+fee\n\n"
        "• /stats → Group stats\n"
        "• /gstats → Global stats per admin (24h reset)\n"
        "• /addadmin user_id → Owner only\n"
        "• /removeadmin user_id → Owner only"
    )

# === ADMIN MANAGEMENT ===
@bot.message_handler(commands=["addadmin"])
def add_admin(msg):
    if msg.from_user.id != OWNER_ID:
        return bot.reply_to(msg, "⛔ Only Owner can add admins.")
    try:
        uid = int(msg.text.split()[1])
        if uid not in admins:
            admins.append(uid)
        bot.reply_to(msg, f"✅ Added admin: {uid}")
    except:
        bot.reply_to(msg, "❌ Usage: /addadmin user_id")

@bot.message_handler(commands=["removeadmin"])
def remove_admin(msg):
    if msg.from_user.id != OWNER_ID:
        return bot.reply_to(msg, "⛔ Only Owner can remove admins.")
    try:
        uid = int(msg.text.split()[1])
        if uid in admins:
            admins.remove(uid)
            bot.reply_to(msg, f"❌ Removed admin: {uid}")
        else:
            bot.reply_to(msg, "⚠️ This user is not an admin.")
    except:
        bot.reply_to(msg, "❌ Usage: /removeadmin user_id")

# === PAYMENT RECEIVED ===
@bot.message_handler(commands=["add", "add+fee"])
def add_deal(msg):
    global trade_id
    if not is_admin(msg.from_user.id):
        return bot.reply_to(msg, "⛔ Only Admin can add deal.")
    if not msg.reply_to_message:
        return bot.reply_to(msg, "⚠️ Reply to deal form with /add or /add+fee")

    buyer, seller, amount = extract_form(msg.reply_to_message.text)
    if not buyer or not seller or not amount:
        return bot.reply_to(msg, "❌ Could not extract Buyer/Seller/Amount.")

    admin_user = f"@{msg.from_user.username}" if msg.from_user.username else str(msg.from_user.id)
    trades[trade_id] = {"buyer": buyer, "seller": seller, "amount": amount, "status": "open", "chat_id": msg.chat.id, "admin": admin_user}

    if msg.text.startswith("/add+fee"):
        fee, total = calc_fee(amount)
        fee_line = f"💰 Fee     : 3% (₹{fee})\n🧤TOTAL : ₹{total}"
    else:
        fee_line = "💰 Fee     : ₹0"

    text = f"""✅ PAYMENT RECEIVED
────────────────
👤 Buyer  : {buyer}
👤 Seller : {seller}
💸 Received : ₹{amount}
🆔 Trade ID : #TID{trade_id}
{fee_line}
CONTINUE DEAL ❤️
────────────────"""

    bot.send_message(msg.chat.id, text)
    bot.send_message(target_channel, text.replace("✅ PAYMENT RECEIVED", "📜 Payment Received (Log)"))
    trade_id += 1

# === DEAL COMPLETED ===
@bot.message_handler(commands=["done", "done+fee"])
def done_deal(msg):
    if not is_admin(msg.from_user.id):
        return bot.reply_to(msg, "⛔ Only Admin can complete deal.")
    if not msg.reply_to_message:
        return bot.reply_to(msg, "⚠️ Reply to deal with /done or /done+fee")

    tid = None
    for word in msg.reply_to_message.text.split():
        if word.startswith("#TID"):
            tid = int(word.replace("#TID", ""))
    if not tid or tid not in trades:
        return bot.reply_to(msg, "❌ Trade not found.")

    deal = trades[tid]
    amount, buyer, seller, admin_user = deal["amount"], deal["buyer"], deal["seller"], deal["admin"]
    trades[tid]["status"] = "completed"
    update_stats(admin_user, "completed", amount)

    if msg.text.startswith("/done+fee"):
        fee, total = calc_fee(amount)
        fee_line = f"💰 Fee     : 3% (₹{fee})\n🧤TOTAL : ₹{total}"
    else:
        fee_line = "💰 Fee     : ₹0"

    text = f"""✅ DEAL COMPLETED
────────────────
👤 Buyer  : {buyer}
👤 Seller : {seller}
💰 Amount : ₹{amount}
🆔 Trade ID : #TID{tid}
{fee_line}
────────────────
🛡️ Escrowed by {admin_user}"""

    bot.send_message(msg.chat.id, text)
    bot.send_message(target_channel, text.replace("✅ DEAL COMPLETED", "📜 Deal Completed (Log)"))

# === REFUND DEAL ===
@bot.message_handler(commands=["refund", "refund+fee"])
def refund_deal(msg):
    if not is_admin(msg.from_user.id):
        return bot.reply_to(msg, "⛔ Only Admin can refund deal.")
    if not msg.reply_to_message:
        return bot.reply_to(msg, "⚠️ Reply to deal with /refund or /refund+fee")

    tid = None
    for word in msg.reply_to_message.text.split():
        if word.startswith("#TID"):
            tid = int(word.replace("#TID", ""))
    if not tid or tid not in trades:
        return bot.reply_to(msg, "❌ Trade not found.")

    deal = trades[tid]
    amount, buyer, seller, admin_user = deal["amount"], deal["buyer"], deal["seller"], deal["admin"]
    trades[tid]["status"] = "refunded"
    update_stats(admin_user, "refunded", amount)

    if msg.text.startswith("/refund+fee"):
        fee, total = calc_fee(amount)
        fee_line = f"💰 Fee     : 3% (₹{fee})\n🧤TOTAL : ₹{total}"
    else:
        fee_line = "💰 Fee     : ₹0"

    text = f"""❌ REFUND COMPLETED
────────────────
👤 Buyer  : {buyer}
👤 Seller : {seller}
💰 Refund : ₹{amount}
🆔 Trade ID : #TID{tid}
{fee_line}
────────────────
🛡️ Escrowed by {admin_user}"""

    bot.send_message(msg.chat.id, text)
    bot.send_message(target_channel, text.replace("❌ REFUND COMPLETED", "📜 Refund Completed (Log)"))

# === STATS ===
@bot.message_handler(commands=["stats"])
def stats(msg):
    chat_id = msg.chat.id
    total = sum(1 for t in trades.values() if t["chat_id"] == chat_id)
    completed = sum(1 for t in trades.values() if t["chat_id"] == chat_id and t["status"] == "completed")
    refunded = sum(1 for t in trades.values() if t["chat_id"] == chat_id and t["status"] == "refunded")
    volume = sum(t["amount"] for t in trades.values() if t["chat_id"] == chat_id)

    bot.reply_to(msg, f"""📊 Group Stats
Total Trades: {total}
Completed: {completed}
Refunded: {refunded}
Total Volume: ₹{volume}""")

# === GLOBAL STATS PER ADMIN ===
@bot.message_handler(commands=["gstats"])
def gstats(msg):
    if not is_admin(msg.from_user.id):
        return bot.reply_to(msg, "⛔ Admin only command.")

    reset_stats()
    response = "🌐 Global Stats (Last 24h)\n"
    for admin, s in stats_24h.items():
        hold = get_hold(admin)
        response += f"""
Escrowed by : {admin}
Hold        : ₹{hold}
Completed   : {s['completed']}
Refunded    : {s['refunded']}
Total Trades: {s['trades']}
Volume      : ₹{s['volume']}
"""
    bot.reply_to(msg, response)

# === RUN ===
bot.infinity_polling()
