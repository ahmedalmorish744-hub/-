import asyncio
import re
import os
import json
import time
import random
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait, RPCError, BadRequest, SessionPasswordNeeded, PhoneCodeInvalid, PhoneNumberInvalid
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatType
from tqdm.asyncio import tqdm

# --- إعدادات المستخدم ---
API_ID = 33957094
API_HASH = "35e04f65846f09700aac0696a59f1a37"
BOT_TOKEN = "8568132127:AAG-4Mxkj7WxpQcVwUcX6GdGHRAfEMjQs_8"
ADMIN_ID = 7853478744
DATA_FILE = "userbot_data.json"

# --- تعريف كائن البوت ---
app = Client("fast_auto_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- متغيرات الحالة ---
is_posting = False
waiting_for_input = {} # {user_id: 'state'}
USERBOT_SESSIONS = {} # {session_name: Client_object}
MESSAGES = {} # {msg_id: {'chat_id': int, 'msg_id': int, 'wait_time': int, 'enabled': bool}}
SETTINGS = {
    'save_mode': True,
    'sleep_mode': False,
    'timestamp': True,
    'sleep_start': 2, # 2 AM
    'sleep_end': 8,   # 8 AM
    'post_interval_min': 300, # 5 minutes
    'post_interval_max': 600  # 10 minutes
}

# --- دالة تحميل وحفظ البيانات ---
def load_data():
    global MESSAGES, SETTINGS
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                MESSAGES.update(data.get('messages', {}))
                SETTINGS.update(data.get('settings', {}))
        except Exception as e:
            print(f"Error loading data: {e}")

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({'messages': MESSAGES, 'settings': SETTINGS}, f, indent=4, ensure_ascii=False)

# --- دالة تحميل الجلسات عند بدء تشغيل البوت ---
async def load_userbots():
    global USERBOT_SESSIONS
    print("جاري تحميل جلسات المستخدمين...")
    for file in os.listdir("."):
        if file.endswith(".session") and file != "fast_auto_bot.session":
            session_name = file.replace(".session", "")
            try:
                user_client = Client(session_name, api_id=API_ID, api_hash=API_HASH)
                await user_client.start()
                USERBOT_SESSIONS[session_name] = user_client
                print(f"✅ تم تحميل الجلسة: {session_name}")
            except Exception as e:
                print(f"❌ فشل تحميل الجلسة {session_name}: {e}")
    print(f"تم تحميل {len(USERBOT_SESSIONS)} جلسة.")

# --- لوحات المفاتيح ---
def get_main_menu():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🚀 بدء الإرسال", callback_data="start_post"),
                InlineKeyboardButton("🛑 إيقاف الإرسال", callback_data="stop_post")
            ],
            [
                InlineKeyboardButton("رسائلي", callback_data="messages_menu"),
                InlineKeyboardButton("المجموعات المضافة", callback_data="groups_menu")
            ],
            [
                InlineKeyboardButton("إدارة الحسابات", callback_data="accounts_menu"),
                InlineKeyboardButton("الإعدادات", callback_data="settings_menu")
            ],
            [
                InlineKeyboardButton("قناتنا", url="http://t.me/almorishbot"),
                InlineKeyboardButton("العربية", callback_data="lang_ar")
            ]
        ]
    )

def get_settings_menu():
    save_mode_text = "✅ وضع الحفظ" if SETTINGS['save_mode'] else "❌ وضع الحفظ"
    sleep_mode_text = "✅ وضع النوم" if SETTINGS['sleep_mode'] else "❌ وضع النوم"
    timestamp_text = "✅ اسم الوقت" if SETTINGS['timestamp'] else "❌ اسم الوقت"
    
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(save_mode_text, callback_data="toggle_save_mode")],
            [InlineKeyboardButton(sleep_mode_text, callback_data="toggle_sleep_mode")],
            [InlineKeyboardButton(timestamp_text, callback_data="toggle_timestamp")],
            [InlineKeyboardButton("تعديل فترات الانتظار", callback_data="edit_intervals")],
            [InlineKeyboardButton("رجوع", callback_data="main_menu")]
        ]
    )

def get_messages_menu():
    buttons = []
    for msg_id, msg_data in MESSAGES.items():
        status = "✅" if msg_data['enabled'] else "❌"
        buttons.append([InlineKeyboardButton(f"{status} رسالة {msg_id}", callback_data=f"view_msg_{msg_id}")])
    
    buttons.append([InlineKeyboardButton("➕ إضافة رسالة جديدة", callback_data="add_new_message")])
    buttons.append([InlineKeyboardButton("رجوع", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)

def get_message_actions(msg_id):
    msg_data = MESSAGES.get(msg_id, {})
    status_text = "تعطيل" if msg_data.get('enabled', True) else "تفعيل"
    
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"تعديل الانتظار ({msg_data.get('wait_time', 300)} ث)", callback_data=f"edit_wait_{msg_id}")],
            [InlineKeyboardButton(status_text, callback_data=f"toggle_msg_{msg_id}")],
            [InlineKeyboardButton("حذف الرسالة", callback_data=f"delete_msg_{msg_id}")],
            [InlineKeyboardButton("رجوع", callback_data="messages_menu")]
        ]
    )

def get_accounts_menu():
    buttons = []
    for session_name in USERBOT_SESSIONS.keys():
        buttons.append([InlineKeyboardButton(f"✅ {session_name}", callback_data=f"remove_account_{session_name}")])
    
    buttons.append([InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account")])
    buttons.append([InlineKeyboardButton("رجوع", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)

# --- دوال مساعدة ---
def extract_links(text):
    pattern = r"(https?://t\.me/(?:\+|joinchat/)?[\w-]+)"
    return re.findall(pattern, text)

def is_sleep_time():
    if not SETTINGS['sleep_mode']:
        return False
    now_hour = time.localtime().tm_hour
    start = SETTINGS['sleep_start']
    end = SETTINGS['sleep_end']
    
    if start < end:
        return start <= now_hour < end
    else:
        return now_hour >= start or now_hour < end

# --- معالج الأوامر النصية ---
@app.on_message(filters.user(ADMIN_ID) & filters.command("start", prefixes="/"))
async def start_command_handler(client, message):
    await client.send_message(message.chat.id, "مرحباً بك في سورس النشر المتطور!", reply_markup=get_main_menu())

# --- معالج الرسائل النصية ---
@app.on_message(filters.user(ADMIN_ID) & ~filters.command(["start"]))
async def main_message_handler(client, message):
    user_id = message.from_user.id
    state = waiting_for_input.get(user_id)

    if state == 'waiting_for_message':
        msg_id = str(len(MESSAGES) + 1)
        MESSAGES[msg_id] = {
            'chat_id': message.chat.id,
            'msg_id': message.id,
            'wait_time': SETTINGS['post_interval_min'],
            'enabled': True
        }
        save_data()
        del waiting_for_input[user_id]
        await message.reply_text(f"✅ **تم حفظ الرسالة رقم {msg_id} بنجاح!**", reply_markup=get_main_menu())
        return

    if state == 'waiting_for_phone':
        phone_number = message.text.strip()
        try:
            user_client = Client(str(user_id), api_id=API_ID, api_hash=API_HASH)
            await user_client.connect()
            sent_code = await user_client.send_code(phone_number)
            waiting_for_input[user_id] = {'state': 'waiting_for_code', 'phone': phone_number, 'hash': sent_code.phone_code_hash, 'client': user_client}
            await message.reply_text("✅ **تم إرسال كود التحقق!** يرجى إرساله الآن.")
        except Exception as e:
            await message.reply_text(f"❌ **خطأ:** {e}", reply_markup=get_main_menu())
            if user_id in waiting_for_input: del waiting_for_input[user_id]
        return

    if isinstance(state, dict) and state.get('state') == 'waiting_for_code':
        code = message.text.strip()
        user_client = state['client']
        try:
            await user_client.sign_in(phone_number=state['phone'], phone_code_hash=state['hash'], phone_code=code)
            USERBOT_SESSIONS[str(user_id)] = user_client
            del waiting_for_input[user_id]
            await message.reply_text("🎉 **تم تسجيل الدخول بنجاح!**", reply_markup=get_main_menu())
        except Exception as e:
            await message.reply_text(f"❌ **خطأ:** {e}", reply_markup=get_main_menu())
        return

    links = extract_links(message.text)
    if links and USERBOT_SESSIONS:
        user_client = list(USERBOT_SESSIONS.values())[0]
        await message.reply_text(f"🚀 جاري الانضمام لـ {len(links)} رابط...")
        for link in links:
            try:
                await user_client.join_chat(link)
                await asyncio.sleep(2)
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception:
                pass
        await message.reply_text("✅ انتهت عملية الانضمام.")

# --- دالة النشر ---
async def fast_poster():
    global is_posting
    while is_posting:
        if is_sleep_time():
            await asyncio.sleep(3600)
            continue
        
        enabled_messages = {k: v for k, v in MESSAGES.items() if v['enabled']}
        if not enabled_messages or not USERBOT_SESSIONS:
            is_posting = False
            break

        for session_name, user_client in USERBOT_SESSIONS.items():
            if not is_posting: break
            try:
                async for dialog in user_client.get_dialogs():
                    if not is_posting: break
                    if dialog.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                        for msg_id, msg_data in enabled_messages.items():
                            try:
                                await user_client.copy_message(chat_id=dialog.chat.id, from_chat_id=msg_data['chat_id'], message_id=msg_data['msg_id'])
                                if SETTINGS['timestamp']:
                                    await user_client.send_message(dialog.chat.id, f"**تم النشر في:** {time.strftime('%Y-%m-%d %H:%M:%S')}", disable_notification=True)
                                
                                wait_time = msg_data['wait_time']
                                if SETTINGS['save_mode']:
                                    wait_time += random.randint(0, 300)
                                await asyncio.sleep(wait_time)
                            except FloodWait as e:
                                await asyncio.sleep(e.value)
                            except Exception:
                                pass
            except Exception:
                pass
        await asyncio.sleep(10)

# --- معالج الأزرار ---
@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    global is_posting
    user_id = callback_query.from_user.id
    if user_id != ADMIN_ID:
        await callback_query.answer("غير مسموح لك!", show_alert=True)
        return

    data = callback_query.data
    await callback_query.answer()

    if data == "main_menu":
        await callback_query.edit_message_text("⚡ **لوحة تحكم سورس النشر المتطور** ⚡", reply_markup=get_main_menu())
    elif data == "start_post":
        if not is_posting:
            is_posting = True
            asyncio.create_task(fast_poster())
            await callback_query.edit_message_text("🚀 **بدأ الإرسال!**", reply_markup=get_main_menu())
    elif data == "stop_post":
        is_posting = False
        await callback_query.edit_message_text("🛑 **تم إيقاف الإرسال.**", reply_markup=get_main_menu())
    elif data == "messages_menu":
        await callback_query.edit_message_text("📝 **إدارة الرسائل**", reply_markup=get_messages_menu())
    elif data == "add_new_message":
        waiting_for_input[user_id] = 'waiting_for_message'
        await callback_query.edit_message_text("أرسل الرسالة الآن.")
    elif data == "accounts_menu":
        await callback_query.edit_message_text("👤 **إدارة الحسابات**", reply_markup=get_accounts_menu())
    elif data == "add_account":
        waiting_for_input[user_id] = 'waiting_for_phone'
        await callback_query.edit_message_text("أرسل رقم الهاتف بصيغة دولية.")
    elif data == "settings_menu":
        await callback_query.edit_message_text("⚙️ **الإعدادات**", reply_markup=get_settings_menu())

# --- تشغيل البوت ---
if __name__ == "__main__":
    load_data()
    print("🚀 البوت جاهز للعمل...")
    app.start()
    # تشغيل تحميل الحسابات في الخلفية
    app.loop.create_task(load_userbots())
    idle()
    app.stop()
