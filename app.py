# WAJIB: Monkey patch dari gevent di baris paling atas
from gevent import monkey
monkey.patch_all()
import gevent

import subprocess
import requests
import time
import re
import os
from flask import Flask, render_template
from flask_socketio import SocketIO

app = Flask(__name__)
# Menggunakan gevent sebagai async_mode modern
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# ==========================================
# KONFIGURASI AI & RAILWAY VARIABLES
# ==========================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") 
API_URL = "https://api.bluesminds.com/v1/chat/completions"
MODEL_AI = "gpt-4o"
WALLET_KEY = os.getenv("WALLET_KEY") 

UPDATE_BALANCE_EVERY = 5 

stats = {
    "balance": "0.0",
    "success": 0,
    "failed": 0,
    "current_q": "Menghubungkan ke mesin bot...",
    "logs": []
}

def clean_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def add_log(msg, type="INFO"):
    t = time.strftime("%H:%M:%S")
    emojis = {"INFO": "⚪", "OK": "🟢", "ERROR": "🔴", "WARN": "🟡", "AI": "🤖", "BANK": "🏦"}
    entry = f"[{t}] {emojis.get(type, 'ℹ️')} {msg}"
    
    stats["logs"].insert(0, entry)
    if len(stats["logs"]) > 40: stats["logs"].pop()
    socketio.emit('update', stats)

def setup_wallet():
    if not WALLET_KEY:
        add_log("ERROR FATAL: WALLET_KEY tidak ditemukan di Variables Railway!", "ERROR")
        return False
        
    config_path = os.path.expanduser("~/.config/nara")
    os.makedirs(config_path, exist_ok=True)
    with open(f"{config_path}/id.json", "w") as f:
        f.write(WALLET_KEY)
    add_log("Wallet ID.json berhasil dikonfigurasi dari Railway.", "OK")
    return True

def sync_blockchain_balance():
    try:
        res = subprocess.run(["npx", "naracli", "balance"], capture_output=True, text=True, timeout=20)
        output = clean_ansi(res.stdout + res.stderr)
        match = re.search(r"Balance:\s*([\d\.]+)", output)
        if match:
            stats["balance"] = match.group(1)
            add_log(f"Saldo Tersinkronisasi: {stats['balance']} NARA", "BANK")
            socketio.emit('update', stats)
    except:
        add_log("Gagal sinkronisasi saldo (Blockchain sibuk)", "WARN")

def ask_ai(question, is_mc, previous_attempts=None):
    if is_mc:
        system_msg = "QUIZ MODE: MULTIPLE CHOICE. Output ONLY the single letter (A, B, C, or D)."
    else:
        system_msg = "QUIZ MODE: ESSAY. Output ONLY the specific word/term. NEVER output just a single letter."

    prompt_retry = f"\n\nNote: Do NOT use these wrong answers: {', '.join(previous_attempts)}" if previous_attempts else ""

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
