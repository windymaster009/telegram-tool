import asyncio
import threading
import os
import json
import time
import traceback
from io import BytesIO
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
from telethon import TelegramClient, utils
from telethon.errors import SessionPasswordNeededError, FloodWaitError
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
SCRAPE_DELAY = 0.6
CONFIG_FILE = "config.json"
TRANSFER_HISTORY_FILE = "transfer_history.jsonl"
TD_MARKER = "[td]"
# =========================================

client = None
bot_running = False
log_queue = []
td_destinations = {}
transfer_history = set()

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
    if value.startswith("@") or value.startswith("http://") or value.startswith("https://"):
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


def entity_title(entity):
    return (
        getattr(entity, "title", None)
        or getattr(entity, "username", None)
        or getattr(entity, "first_name", None)
        or "Unknown"
    )


def peer_id(entity):
    try:
        return utils.get_peer_id(entity)
    except Exception:
        return getattr(entity, "id", 0)


def media_description(msg):
    ext = ""
    name = ""

    if getattr(msg, "file", None):
        ext = (getattr(msg.file, "ext", None) or "").replace(".", "").upper()
        name = getattr(msg.file, "name", None) or ""

    if getattr(msg, "photo", None):
        kind = "Image"
        ext = ext or "JPG"
    elif getattr(msg, "video", None):
        kind = "Video"
        ext = ext or "MP4"
    elif getattr(msg, "gif", None):
        kind = "GIF"
        ext = ext or "GIF"
    elif getattr(msg, "voice", None):
        kind = "Voice"
        ext = ext or "OGG"
    elif getattr(msg, "audio", None):
        kind = "Audio"
        ext = ext or "AUDIO"
    elif getattr(msg, "sticker", None):
        kind = "Sticker"
        ext = ext or "WEBP"
    else:
        kind = "File"
        ext = ext or "FILE"

    if name:
        return f"{ext} - {kind} ({name})"
    return f"{ext} - {kind}"


def load_transfer_history():
    history = set()
    if not os.path.exists(TRANSFER_HISTORY_FILE):
        return history

    try:
        with open(TRANSFER_HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                history_key = line.strip()
                if history_key:
                    history.add(history_key)
    except Exception as e:
        log(f"⚠️ Could not read transfer history: {e}")

    return history


def remember_transfer(history_key):
    transfer_history.add(history_key)
    try:
        with open(TRANSFER_HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(history_key + "\\n")
    except Exception as e:
        log(f"⚠️ Could not save transfer history: {e}")


def is_protected_copy_error(exc):
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    protected_markers = (
        "chatforwardsrestricted",
        "forwards restricted",
        "forwarding is restricted",
        "protected content",
        "chat_forwards_restricted",
    )
    return any(marker in name or marker in text for marker in protected_markers)


transfer_history = load_transfer_history()

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
        name = entity_title(entity)

        # Keep channel preview in memory. No preview/source media is written to disk.
        photo_bytes = await client.download_profile_photo(entity, file=bytes)

        def ui():
            channel_name_label.config(text=name)
            if photo_bytes:
                img = Image.open(BytesIO(photo_bytes))
                img.thumbnail((80, 80))
                tk_img = ImageTk.PhotoImage(img.copy())
                channel_photo_label.config(image=tk_img, text="")
                channel_photo_label.image = tk_img
            else:
                channel_photo_label.config(image="", text="No Photo")
                channel_photo_label.image = None

        root.after(0, ui)

    except:
        log("⚠️ Preview load failed")


# ---------- TELEGRAM DRIVE DESTINATIONS ----------
async def discover_td_destinations(preferred=""):
    global td_destinations

    found = {}
    async for dialog in client.iter_dialogs():
        title = entity_title(dialog.entity)
        if TD_MARKER not in title.lower():
            continue

        pid = peer_id(dialog.entity)
        label = f"{title}  ({pid})"
        found[label] = dialog.entity

    td_destinations = dict(sorted(found.items(), key=lambda item: item[0].lower()))

    def ui():
        values = list(td_destinations.keys())
        destination_combo["values"] = values

        selected = ""
        if preferred:
            if preferred in td_destinations:
                selected = preferred
            else:
                for label in values:
                    if label.startswith(preferred + "  ("):
                        selected = label
                        break

        if not selected and values:
            selected = values[0]

        destination_var.set(selected)
        destination_status.config(text=f"{len(values)} [TD] storage channel(s) found")

    root.after(0, ui)
    log(f"☁ Found {len(found)} Telegram Drive destination(s)")


# ---------- SERVER-SIDE COPY ----------
async def copy_message_server_side(destination, msg):
    while bot_running:
        try:
            # Telegram copies the existing media server-side. The file is not
            # downloaded to this PC and uploaded again.
            await client.forward_messages(destination, msg, drop_author=True)
            return "copied"

        except FloodWaitError as e:
            log(f"⏳ Telegram flood wait: {e.seconds}s")
            for _ in range(e.seconds):
                if not bot_running:
                    return "stopped"
                await asyncio.sleep(1)

        except Exception as e:
            if is_protected_copy_error(e):
                return "protected"
            raise

    return "stopped"


async def transfer_media(source, destination, from_date=None):
    source_entity = await client.get_entity(source)
    destination_entity = destination

    source_pid = peer_id(source_entity)
    destination_pid = peer_id(destination_entity)

    if source_pid == destination_pid:
        raise ValueError("Source and destination cannot be the same channel.")

    log(f"📡 Source: {entity_title(source_entity)}")
    log(f"☁ Destination: {entity_title(destination_entity)}")
    log("🚀 Telegram → Telegram transfer started (no local media download)")

    copied = 0
    duplicates = 0
    protected = 0
    skipped = 0
    failed = 0

    async for msg in client.iter_messages(source_entity):  # NEW → OLD
        if not bot_running:
            log("⛔ Stopped")
            break

        msg_day = msg.date.date()

        if from_date and msg_day < from_date:
            log("⏹ Reached messages older than selected date — stopping")
            break

        if not msg.media or isinstance(msg.media, MessageMediaWebPage):
            skipped += 1
            continue

        history_key = f"{source_pid}:{msg.id}->{destination_pid}"
        if history_key in transfer_history:
            duplicates += 1
            log(f"⏭ Already copied (ID {msg.id})")
            continue

        root.after(0, lambda: progress_bar.config(value=25))
        description = media_description(msg)

        try:
            result = await copy_message_server_side(destination_entity, msg)

            if result == "copied":
                copied += 1
                remember_transfer(history_key)
                root.after(0, lambda: progress_bar.config(value=100))
                log(f"✅ Copied ☁ {description} (ID {msg.id})")

            elif result == "protected":
                protected += 1
                root.after(0, lambda: progress_bar.config(value=0))
                log(f"🔒 Protected media skipped (ID {msg.id})")

            elif result == "stopped":
                break

        except Exception as e:
            failed += 1
            root.after(0, lambda: progress_bar.config(value=0))
            log(f"❌ Failed ID {msg.id}: {e}")

        await asyncio.sleep(SCRAPE_DELAY)

    root.after(0, lambda: progress_bar.config(value=0))
    log("🎉 Done!")
    log(
        "📊 Summary: "
        f"Copied {copied}, Duplicates {duplicates}, "
        f"Protected {protected}, Skipped {skipped}, Failed {failed}"
    )


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
            me = await client.get_me()
            display = getattr(me, "username", None) or getattr(me, "first_name", None) or str(getattr(me, "id", "Telegram user"))
            log(f"✅ Login successful as {display}")
            await discover_td_destinations()
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

def refresh_destinations_click():
    if not client:
        messagebox.showwarning("Login first", "Please login first")
        return

    preferred = destination_var.get().strip()
    asyncio.run_coroutine_threadsafe(discover_td_destinations(preferred), loop)


def start_bot():
    global bot_running
    if not client:
        messagebox.showerror("Error", "Please LOGIN first")
        return

    if bot_running:
        return

    source_raw = channel_entry.get().strip()
    if not source_raw:
        messagebox.showerror("Error", "Enter a source Telegram channel first")
        return

    destination_label = destination_var.get().strip()
    destination = td_destinations.get(destination_label)
    if not destination:
        messagebox.showerror(
            "Error",
            "Choose a [TD] destination channel. Click Refresh [TD] if needed."
        )
        return

    bot_running = True
    source = normalize_channel_id(source_raw)
    date_val = cal.get_date() if mode_var.get() == "date" else None

    async def runner():
        try:
            log("⏳ Resolving source...")
            entity = await verify_channel(source)
            if not entity:
                log("❌ Cannot access source channel")
                return

            await load_channel_preview(entity)
            await transfer_media(entity, destination, date_val)

        except Exception as e:
            log_exception(e)
        finally:
            global bot_running
            bot_running = False
            root.after(0, lambda: progress_bar.config(value=0))

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
root.title("WinDy Telegram → Drive Tool")
root.geometry("1150x680")

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

tk.Label(left, text="Source Channel", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 0))
channel_entry = tk.Entry(left)
channel_entry.pack(fill="x")

tk.Label(left, text="Destination Storage", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 0))
destination_var = tk.StringVar(value="")
destination_combo = ttk.Combobox(left, textvariable=destination_var, state="readonly")
destination_combo.pack(fill="x", pady=(2, 0))
tk.Button(left, text="☁ Refresh [TD] Channels", command=refresh_destinations_click).pack(fill="x", pady=(4, 0))
destination_status = tk.Label(
    left,
    text="Login to detect Telegram Drive [TD] channels",
    fg="#555555",
    wraplength=300,
    justify="left"
)
destination_status.pack(anchor="w", pady=(3, 6))

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
tk.Button(btns, text="▶ COPY TO DRIVE", width=16, command=start_bot).pack(side=tk.LEFT, padx=5)
tk.Button(btns, text="⛔ STOP", width=10, command=stop_bot).pack(side=tk.LEFT)

tk.Label(
    left,
    text="Telegram → Telegram server-side copy.\\nNo source media is saved in downloads/.",
    fg="#444444",
    wraplength=300,
    justify="left"
).pack(anchor="w", pady=(4, 0))

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
