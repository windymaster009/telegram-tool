# WinDy Telegram → Drive Tool

A Python desktop tool built with **Telethon** and **Tkinter** for copying Telegram media directly into Telegram Drive storage channels.

The transfer is **Telegram → Telegram**. Source photos, videos, documents, audio, and other media are not first downloaded into a local `downloads/` folder.

## Features

- Login with a normal Telegram user account through Telethon
- Resolve a source channel from URL, username, or Telegram peer ID
- Automatically discover chats/channels whose title contains `[TD]`
- Pick the destination Telegram Drive storage channel from a dropdown
- Copy media server-side with `drop_author=True`
- Transfer all media or stop when messages become older than a selected date
- Duplicate protection using source message ID + source/destination peer IDs
- Flood-wait handling
- Protected-content detection and skip logging
- In-memory channel preview instead of saving the preview image to disk
- Stop button and activity summary

## Telegram Drive integration

Telegram Drive already treats channels containing `[TD]` in the title as storage folders, for example:

```text
Image [TD]
XMPay [TD]
JABpay [TD]
GOLD [TD]
MKpay [TD]
```

The Telegram account used by this tool must be able to read the source and post into the selected `[TD]` destination.

Protected Telegram content that cannot be forwarded/copied is skipped instead of being downloaded locally.

## Local files

The app still keeps small runtime/authentication files locally:

- Telethon session file
- encrypted `config.json`
- `key.key`
- `transfer_history.jsonl` for duplicate detection

These contain session/configuration/metadata, **not the transferred media files**.

## Requirements

- Windows 10/11
- Python 3.9+
- Telegram API ID and API Hash

## Install

```bash
git clone https://github.com/windymaster009/telegram-tool.git
cd telegram-tool
pip install -r requirements.txt
python media_menu.py
```

## Usage

1. Enter API ID, API Hash, and phone number.
2. Click **LOGIN** and complete the Telegram login if requested.
3. Enter the source Telegram channel.
4. Select the destination `[TD]` channel detected from your Telegram account.
5. Choose **All Media** or **From Date**.
6. Click **COPY TO DRIVE**.

The destination media will then show up in Telegram Drive because the `[TD]` channel itself is the storage backend.
