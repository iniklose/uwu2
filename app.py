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
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_AI = "qwen/qwen3.6-plus:free"
WALLET_KEY = os.getenv("WALLET_KEY") 

UPDATE_BALANCE_EVERY = 5 

stats = {
    "balance": "0.0",
    "success": 0,
    "failed": 0,
    "current_q": "Menghubungkan ke mesin bot...",
    "current_r": "-", # Indikator Ronde
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
        "model": MODEL_AI,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"Question: {question}{prompt_retry}\n\nAnswer:"}
        ],
        "temperature": 0.3 if previous_attempts else 0.0
    }
    
    try:
        res = requests.post(API_URL, headers=headers, json=payload, timeout=15)
        ans = res.json()['choices'][0]['message']['content'].strip().split('\n')[0]
        final = re.sub(r"^(Answer|Result|Option):\s*", "", ans, flags=re.IGNORECASE).strip()
        final = re.sub(r"^[A-Z][\.\)\-\s]+", "", final).strip()
        
        if not is_mc and len(final) <= 1: return None 
        return final if len(final) == 1 else final.title()
    except:
        return None

def submit_answer(answer):
    if not answer: return False
    add_log(f"Mengirim Jawaban: {answer}", "INFO")
    try:
        res = subprocess.run(["npx", "naracli", "quest", "answer", answer], capture_output=True, text=True, timeout=60)
        out = clean_ansi(res.stdout + "\n" + res.stderr).strip()
        
        if any(w in out.lower() for w in ["success", "reward", "congratulations", "submitted"]):
            stats["success"] += 1
            rew_match = re.search(r"(?:received|reward):\s*([\d\.]+)", out.lower())
            if rew_match:
                add_log(f"Sukses! Mendapatkan +{rew_match.group(1)} NARA", "OK")
            
            if stats["success"] % UPDATE_BALANCE_EVERY == 0:
                sync_blockchain_balance()
            
            socketio.emit('update', stats)
            return True
        else:
            add_log(f"Gagal: {out[:40]}...", "WARN")
            return False
    except Exception as e:
        add_log(f"Kesalahan Sistem: {str(e)[:30]}", "ERROR")
        return False

def bot_engine():
    gevent.sleep(3) 
    add_log("Memulai Mesin Pemantau Kuis V19.0...", "AI")
    
    if not setup_wallet(): return
    sync_blockchain_balance()
    
    stats["current_q"] = "Siaga! Memantau ronde kuis baru..."
    socketio.emit('update', stats)
    
    last_r = None
    while True:
        try:
            gevent.sleep(2) # Polling kuis setiap 2 detik
            
            res_q = subprocess.run(["npx", "naracli", "quest", "get"], capture_output=True, text=True)
            out_q = clean_ansi(res_q.stdout)
            
            q_match = re.search(r"Question:\s*(.*?)\s*Round:", out_q, re.DOTALL)
            r_match = re.search(r"Round:\s*#(\d+)", out_q)

            if q_match and r_match:
                q_text = q_match.group(1).strip()
                curr_r = r_match.group(1)
                
                if curr_r != last_r and "0 remaining" not in out_q:
                    stats["current_r"] = curr_r # Update Info Ronde
                    stats["current_q"] = q_text
                    socketio.emit('update', stats)
                    add_log(f"🔥 Kuis Baru Terdeteksi! Ronde #{curr_r}", "AI")
                    
                    is_mc = bool(re.search(r"\b[A-D][\.\)]\s", q_text))
                    history = []; success = False
                    max_tries = 4 if not is_mc else 1

                    for i in range(max_tries):
                        ans = ask_ai(q_text, is_mc, previous_attempts=history)
                        if not ans: continue
                        
                        success = submit_answer(ans)
                        if success: break
                        
                        history.append(ans)
                        if is_mc:
                            add_log("Mencoba Brute-force A/B/C/D...", "WARN")
                            for char in ["A", "B", "C", "D"]:
                                if char == ans: continue
                                if submit_answer(char): 
                                    success = True; break
                            break
                        gevent.sleep(3.5)

                    if not success: stats["failed"] += 1
                    last_r = curr_r
                    stats["current_q"] = "Siaga! Memantau ronde selanjutnya..."
                    socketio.emit('update', stats)

        except Exception:
            gevent.sleep(2)

# --- ROUTES & SOCKET EVENTS ---
@app.route('/')
def index():
    return render_template('index.html')

# Fitur Anti-Blank: Otomatis kirim data saat web dibuka/direload
@socketio.on('connect')
def handle_connect():
    print("Client Terhubung! Sinkronisasi UI...")
    socketio.emit('update', stats)

if __name__ == '__main__':
    # Jalankan bot sebagai background task bawaan SocketIO
    socketio.start_background_task(bot_engine)
    
    # Jalankan server web
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
