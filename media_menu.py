import asyncio
import threading
import os
import json
import time
import traceback
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import MessageMediaWebPage
from tkcalendar import DateEntry
from PIL import Image, ImageTk
from datetime import timezone
from datetime import datetime, timezone, timedelta
from cryptography.fernet import Fernet

# ---------- ENCRYPTION ----------
KEY_FILE = "key.key"

def load_key():
    if os.path.exists(KEY_FILE):
        try:
            key = open(KEY_FILE, "rb").read()
            Fernet(key)  # validate key
            return key
        except Exception:
            pass

    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(key)
    return key

key = load_key()
fernet = Fernet(key)

# ================= CONFIG =================
SESSION_NAME = "media_gui_session"
DOWNLOAD_DIR = "downloads"
SCRAPE_DELAY = 0.6
CONFIG_FILE = "config.json"
# =========================================

client = None
bot_running = False
log_queue = []

user_input_value = None
user_input_event = asyncio.Event()

def on_user_input(text):
    global user_input_value
    user_input_value = text
    loop.call_soon_threadsafe(user_input_event.set)

# ---------- ASYNC LOOP ----------
loop = asyncio.new_event_loop()

def start_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=start_loop, daemon=True).start()

# ---------- LOG ----------
def log(msg):
    timestamp = time.strftime("%H:%M:%S")
    log_queue.append(f"[{timestamp}] {msg}")

def log_exception(e):
    log(str(e))
    log(traceback.format_exc())

def update_logs():
    while log_queue:
        terminal.insert(tk.END, log_queue.pop(0) + "\n")
        terminal.see(tk.END)
    root.after(300, update_logs)


def save_config(api_id, api_hash, phone):
    data = json.dumps({
        "api_id": api_id,
        "api_hash": api_hash,
        "phone": phone
    }).encode()

    encrypted = fernet.encrypt(data)

    with open(CONFIG_FILE, "wb") as f:
        f.write(encrypted)

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"api_id": "", "api_hash": "", "phone": ""}

    with open(CONFIG_FILE, "rb") as f:
        encrypted = f.read()

    decrypted = fernet.decrypt(encrypted)
    return json.loads(decrypted.decode())


# ---------- HELPERS ----------
def normalize_channel_id(value: str):
    value = value.strip()
    if value.startswith("@"):
        return value
    try:
        num = int(value)
        if str(num).startswith("-100"):
            return num
        if str(num).startswith("-"):
            return int("-100" + str(num)[1:])
        return int("-100" + str(num))
    except:
        return value

# ---------- TELEGRAM ----------
async def telegram_login(api_id, api_hash, phone):
    global client
    client = TelegramClient(SESSION_NAME, api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        await client.send_code_request(phone)
        code = simpledialog.askstring("Telegram Login", "Enter login code:")
        await client.sign_in(phone, code)

        try:
            await client.sign_in(password=simpledialog.askstring(
                "Telegram Login",
                "2FA Password:",
                show="*"
            ))
        except SessionPasswordNeededError:
            pass

async def wait_for_user_input(prompt):
    log(prompt)
    user_input_event.clear()
    await user_input_event.wait()
    return user_input_value

async def telegram_login(api_id, api_hash, phone):
    global client
    client = TelegramClient(SESSION_NAME, api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        await client.send_code_request(phone)

        code = await wait_for_user_input(
            "📩 Enter Telegram login code and press SEND"
        )

        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            password = await wait_for_user_input(
                "🔐 Enter 2FA password and press SEND"
            )
            await client.sign_in(password=password)


async def verify_channel(source):
    try:
        return await client.get_entity(source)
    except:
        return None

async def load_channel_preview(source):
    try:
        entity = await client.get_entity(source)
        name = getattr(entity, "title", "Unknown")

        photo = await client.download_profile_photo(entity, file="__preview.jpg")

        def ui():
            channel_name_label.config(text=name)
            if photo and os.path.exists(photo):
                img = Image.open(photo).resize((80, 80))
                tk_img = ImageTk.PhotoImage(img)
                channel_photo_label.config(image=tk_img)
                channel_photo_label.image = tk_img
            else:
                channel_photo_label.config(image="", text="No Photo")

        root.after(0, ui)

    except:
        log("⚠️ Preview load failed")

# ---------- PROGRESS ----------
def progress_callback(current, total):
    if total:
        percent = (current / total) * 100
        root.after(0, lambda v=percent: progress_bar.config(value=v))

# ---------- DOWNLOAD ----------
async def download_media(source, from_date=None):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    entity = await client.get_entity(source)

    log(f"📥 Downloading from {entity.title}")

    async for msg in client.iter_messages(entity):  # NEW → OLD

        if not bot_running:
            log("⛔ Stopped")
            return

        if not msg.media or isinstance(msg.media, MessageMediaWebPage):
            continue

        msg_day = msg.date.date()  # ✅ UTC → DATE ONLY

        # STOP once we go older than selected date
        if from_date and msg_day < from_date:
            log("⏹ Reached messages older than selected date — stopping")
            break

        progress_bar["value"] = 0
        filename = f"{msg_day}_{msg.id}"

        await msg.download_media(
            file=os.path.join(DOWNLOAD_DIR, filename),
            progress_callback=progress_callback
        )

        log(f"✅ Downloaded {filename}")
        await asyncio.sleep(SCRAPE_DELAY)

    log("🎉 Done!")


# ---------- BUTTONS ----------
def login_click():
    async def runner():
        try:
            log("🔐 Logging in...")
            await telegram_login(
                int(api_id_entry.get()),
                api_hash_entry.get(),
                phone_entry.get()
            )
            save_config(api_id_entry.get(), api_hash_entry.get(), phone_entry.get())
            log("✅ Login successful")
        except Exception as e:
            log_exception(e)

    asyncio.run_coroutine_threadsafe(runner(), loop)

def convert_channel_id():
    if not client:
        messagebox.showwarning("Login first", "Please login first")
        return

    raw = channel_entry.get()
    source = normalize_channel_id(raw)

    async def runner():
        entity = await verify_channel(source)
        if not entity:
            log("❌ Cannot resolve channel")
            return

        root.after(0, lambda: channel_entry.delete(0, tk.END))
        root.after(0, lambda: channel_entry.insert(0, str(source)))
        log(f"🔄 Resolved: {entity.title}")
        await load_channel_preview(source)

    asyncio.run_coroutine_threadsafe(runner(), loop)

def start_bot():
    global bot_running
    if not client:
        messagebox.showerror("Error", "Please LOGIN first")
        return

    if bot_running:
        return

    bot_running = True
    source = normalize_channel_id(channel_entry.get())
    date_val = cal.get_date() if mode_var.get() == "date" else None

    async def runner():
        try:
            log("⏳ Connecting...")
            entity = await verify_channel(source)
            if not entity:
                log("❌ Cannot access channel")
                return

            await load_channel_preview(source)
            await download_media(source, date_val)

        except Exception as e:
            log_exception(e)
        finally:
            global bot_running
            bot_running = False

    asyncio.run_coroutine_threadsafe(runner(), loop)

def stop_bot():
    global bot_running
    bot_running = False
    log("⛔ Stop requested")

def apply_day_theme():
    root.configure(bg="#F0F0F0")
    left.configure(bg="#F0F0F0")
    right.configure(bg="#F0F0F0")

    for widget in left.winfo_children():
        try:
            widget.configure(bg="#F0F0F0", fg="#000000")
        except:
            pass

    terminal.configure(
        bg="#000000",
        fg="#00ff44",
        insertbackground="#000000"
    )

# ================= UI =================
root = tk.Tk()
root.title("WinDy Media Tool")
root.geometry("1100x600")

toolbar_frame = tk.Frame(root, bd=1, relief=tk.RAISED)


cfg = load_config()

left = tk.Frame(root, width=320, padx=10)
left.pack(side=tk.LEFT, fill=tk.Y)

right = tk.Frame(root, padx=10)
right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

# ---- INPUT BAR (Telegram Code / 2FA input) ----
input_frame = tk.Frame(right)
input_frame.pack(fill="x", pady=4)

input_entry = tk.Entry(input_frame)
input_entry.pack(side=tk.LEFT, fill="x", expand=True, padx=5)

def submit_input():
    text = input_entry.get().strip()
    if text:
        input_entry.delete(0, tk.END)
        on_user_input(text)

tk.Button(input_frame, text="Enter", command=submit_input).pack(side=tk.RIGHT)

tk.Label(left, text="Telegram Login", font=("Segoe UI", 12, "bold")).pack(pady=5)

tk.Label(left, text="API ID").pack(anchor="w")
api_id_entry = tk.Entry(left)
api_id_entry.insert(0, cfg["api_id"])
api_id_entry.pack(fill="x")

tk.Label(left, text="API Hash").pack(anchor="w")
api_hash_entry = tk.Entry(left)
api_hash_entry.insert(0, cfg["api_hash"])
api_hash_entry.pack(fill="x")

tk.Label(left, text="Phone").pack(anchor="w")
phone_entry = tk.Entry(left)
phone_entry.insert(0, cfg["phone"])
phone_entry.pack(fill="x")

tk.Button(left, text="🔐 LOGIN", command=login_click).pack(fill="x", pady=6)
tk.Button(left, text="🔄 Convert Real ID", command=convert_channel_id).pack(fill="x")

tk.Label(left, text="Channel").pack(anchor="w", pady=(10, 0))
channel_entry = tk.Entry(left)
channel_entry.pack(fill="x")

preview_frame = tk.Frame(left)
preview_frame.pack(pady=8)

channel_photo_label = tk.Label(preview_frame)
channel_photo_label.pack()

channel_name_label = tk.Label(preview_frame, font=("Segoe UI", 10, "bold"))
channel_name_label.pack()

mode_var = tk.StringVar(value="all")
tk.Radiobutton(left, text="All Media", variable=mode_var, value="all").pack(anchor="w")
tk.Radiobutton(left, text="From Date", variable=mode_var, value="date").pack(anchor="w")

cal = DateEntry(left, date_pattern="yyyy-mm-dd")
cal.pack(pady=5)

btns = tk.Frame(left)
btns.pack(pady=10)
tk.Button(btns, text="▶ START", width=12, command=start_bot).pack(side=tk.LEFT, padx=5)
tk.Button(btns, text="⛔ STOP", width=12, command=stop_bot).pack(side=tk.LEFT)

tk.Label(right, text="Activity Log", font=("Segoe UI", 12, "bold")).pack(anchor="w")

terminal = scrolledtext.ScrolledText(
    right, bg="#111", fg="#00ff9c", font=("Consolas", 10)
)
terminal.pack(fill=tk.BOTH, expand=True)

progress_bar = ttk.Progressbar(right, mode="determinate")
progress_bar.pack(fill="x", pady=5)
apply_day_theme()

root.after(300, update_logs)
# Set window/taskbar icon
# root.iconbitmap("icon.ico")
root.mainloop()
