"""
JARVIS - Phase 3 - Full Movie Style (Fixed)
Fixes: name memory, face greeting cooldown, tkinter threading crash
"""

import os
import json
import threading
import multiprocessing
import tkinter as tk
import pyttsx3
import sounddevice as sd
import scipy.io.wavfile as wav_writer
import speech_recognition as sr
import webbrowser
import subprocess
import platform
import tempfile
import pickle
import time
import sqlite3
import base64
import psutil
import cv2
from datetime import datetime, timedelta
from typing import Optional
from groq import Groq
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from PIL import ImageGrab
from io import BytesIO

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    SPOTIFY_AVAILABLE = True
except:
    SPOTIFY_AVAILABLE = False

# ── Config ────────────────────────────────────────────────────────────────────
GROQ_API_KEY = "ENTER YOUR GROQ API KEY HERE"
SPOTIFY_CLIENT_ID = ""
SPOTIFY_CLIENT_SECRET = ""
SPOTIFY_REDIRECT_URI = "http://localhost:8888/callback"
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
MORNING_BRIEFING_HOUR = 8
GMAIL_CHECK_INTERVAL = 300
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# ── Shared HUD state ──────────────────────────────────────────────────────────
hud_state = {
    "status": "ONLINE",
    "listening": False,
    "last_command": "",
    "last_response": "",
    "active_app": "",
    "cpu": "0%",
    "ram": "0%",
    "battery": "—",
    "face_detected": False,
}

# ── Memory (SQLite) ───────────────────────────────────────────────────────────
def init_memory():
    conn = sqlite3.connect("jarvis_memory.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS memory (
        key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT, remind_at TEXT, done INTEGER DEFAULT 0)""")
    conn.commit()
    conn.close()

def remember(key: str, value: str):
    conn = sqlite3.connect("jarvis_memory.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO memory (key, value, updated_at) VALUES (?,?,?)",
              (key, value, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def recall(key: str) -> str:
    conn = sqlite3.connect("jarvis_memory.db")
    c = conn.cursor()
    c.execute("SELECT value FROM memory WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

def recall_all() -> dict:
    conn = sqlite3.connect("jarvis_memory.db")
    c = conn.cursor()
    c.execute("SELECT key, value FROM memory")
    rows = c.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

def add_reminder(text: str, remind_at: str):
    conn = sqlite3.connect("jarvis_memory.db")
    c = conn.cursor()
    c.execute("INSERT INTO reminders (text, remind_at) VALUES (?,?)", (text, remind_at))
    conn.commit()
    conn.close()

def get_pending_reminders() -> list:
    conn = sqlite3.connect("jarvis_memory.db")
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("SELECT id, text FROM reminders WHERE done=0 AND remind_at <= ?", (now,))
    rows = c.fetchall()
    conn.close()
    return rows

def mark_reminder_done(reminder_id: int):
    conn = sqlite3.connect("jarvis_memory.db")
    c = conn.cursor()
    c.execute("UPDATE reminders SET done=1 WHERE id=?", (reminder_id,))
    conn.commit()
    conn.close()

# ── TTS ───────────────────────────────────────────────────────────────────────
def _tts_worker(text, voice_index, rate):
    import pyttsx3
    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    if voices:
        engine.setProperty("voice", voices[voice_index].id)
    engine.setProperty("rate", rate)
    engine.setProperty("volume", 1.0)
    engine.say(text)
    engine.runAndWait()
    engine.stop()

def speak(text: str, interruptible: bool = True):
    print(f"\n🤖 JARVIS: {text}\n")
    hud_state["last_response"] = text
    hud_state["status"] = "SPEAKING"
    p = multiprocessing.Process(target=_tts_worker, args=(text, 0, 175))
    p.start()
    if interruptible:
        interrupted = threading.Event()
        def wait_input():
            input("  (Press Enter to interrupt...)\n")
            interrupted.set()
        t = threading.Thread(target=wait_input, daemon=True)
        t.start()
        while p.is_alive() and not interrupted.is_set():
            time.sleep(0.1)
        if p.is_alive():
            p.terminate()
            p.join()
    else:
        p.join()
    hud_state["status"] = "ONLINE"

# ── Speech Recognition ────────────────────────────────────────────────────────
recognizer = sr.Recognizer()
SAMPLE_RATE = 16000
RECORD_SECONDS = 7

def listen() -> Optional[str]:
    hud_state["listening"] = True
    print("🎙️  Listening...")
    try:
        recording = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        sd.wait()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
        wav_writer.write(tmp_path, SAMPLE_RATE, recording)
        with sr.AudioFile(tmp_path) as source:
            audio = recognizer.record(source)
        os.unlink(tmp_path)
        text = recognizer.recognize_google(audio)
        print(f"👤 You: {text}")
        hud_state["last_command"] = text
        hud_state["listening"] = False
        return text
    except sr.UnknownValueError:
        hud_state["listening"] = False
        return None
    except Exception as e:
        hud_state["listening"] = False
        print(f"Listen error: {e}")
        return None

# ── Google Auth ───────────────────────────────────────────────────────────────
def get_google_credentials():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("credentials.json"):
                return None
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
    return creds

# ── Screen Vision ─────────────────────────────────────────────────────────────
def capture_screen_base64() -> str:
    try:
        screenshot = ImageGrab.grab()
        screenshot = screenshot.resize((1280, 720))
        buffer = BytesIO()
        screenshot.save(buffer, format="JPEG", quality=70)
        return base64.b64encode(buffer.getvalue()).decode()
    except:
        return ""

def analyze_screen() -> str:
    img_b64 = capture_screen_base64()
    if not img_b64:
        return f"User is working in: {get_active_window()}"
    try:
        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                {"type": "text", "text": "Describe what's on this screen in 2-3 sentences. Focus on what the user is working on."}
            ]}],
            max_tokens=200,
        )
        return response.choices[0].message.content
    except:
        return f"User is working in: {get_active_window()}"

def get_active_window() -> str:
    try:
        if platform.system() == "Windows":
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value or "Unknown"
    except:
        pass
    return "Unknown"

# ── Face Detection (FIXED — 5 min cooldown) ───────────────────────────────────
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
face_was_present = False
last_greeting_time = 0

def face_detection_loop():
    global face_was_present, last_greeting_time
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("⚠️ Webcam not accessible.")
        return
    while True:
        try:
            ret, frame = cap.read()
            if not ret:
                time.sleep(1)
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
            face_detected = len(faces) > 0
            hud_state["face_detected"] = face_detected
            now_ts = time.time()
            # Only greet if face just appeared AND last greeting was 5+ mins ago
            if face_detected and not face_was_present and (now_ts - last_greeting_time > 300):
                last_greeting_time = now_ts
                user_name = recall("user_name") or "sir"
                hour = datetime.now().hour
                if hour < 12:
                    greeting = f"Good morning, {user_name}."
                elif hour < 17:
                    greeting = f"Welcome back, {user_name}."
                else:
                    greeting = f"Good evening, {user_name}."
                threading.Thread(target=speak, args=(greeting, False), daemon=True).start()
            face_was_present = face_detected
        except Exception as e:
            print(f"Face detection error: {e}")
        time.sleep(2)
    cap.release()

# ── System Stats ──────────────────────────────────────────────────────────────
def system_stats_loop():
    while True:
        try:
            hud_state["cpu"] = f"{psutil.cpu_percent(interval=1):.0f}%"
            hud_state["ram"] = f"{psutil.virtual_memory().percent:.0f}%"
            battery = psutil.sensors_battery()
            if battery:
                charging = "⚡" if battery.power_plugged else "🔋"
                hud_state["battery"] = f"{charging}{battery.percent:.0f}%"
            else:
                hud_state["battery"] = "N/A"
        except:
            pass
        time.sleep(5)

# ── Reminder Monitor ──────────────────────────────────────────────────────────
def reminder_monitor_loop():
    while True:
        try:
            pending = get_pending_reminders()
            for rid, text in pending:
                mark_reminder_done(rid)
                threading.Thread(target=speak, args=(f"Reminder: {text}", False), daemon=True).start()
        except:
            pass
        time.sleep(30)

# ── Proactive Email Monitor ───────────────────────────────────────────────────
last_email_id = None

def email_monitor_loop():
    global last_email_id
    time.sleep(30)
    while True:
        try:
            creds = get_google_credentials()
            if creds:
                service = build("gmail", "v1", credentials=creds)
                results = service.users().messages().list(userId="me", labelIds=["INBOX"], maxResults=1).execute()
                messages = results.get("messages", [])
                if messages:
                    latest_id = messages[0]["id"]
                    if last_email_id is None:
                        last_email_id = latest_id
                    elif latest_id != last_email_id:
                        last_email_id = latest_id
                        data = service.users().messages().get(
                            userId="me", id=latest_id, format="metadata",
                            metadataHeaders=["Subject", "From"]).execute()
                        h = {x["name"]: x["value"] for x in data["payload"]["headers"]}
                        sender = h.get("From", "Someone").split("<")[0].strip()
                        subject = h.get("Subject", "No subject")[:40]
                        threading.Thread(target=speak,
                            args=(f"Sir, new email from {sender}: {subject}", False), daemon=True).start()
        except:
            pass
        time.sleep(GMAIL_CHECK_INTERVAL)

# ── Morning Briefing ──────────────────────────────────────────────────────────
briefing_done_today = None

def morning_briefing_loop():
    global briefing_done_today
    while True:
        now = datetime.now()
        if now.hour == MORNING_BRIEFING_HOUR and briefing_done_today != now.date():
            briefing_done_today = now.date()
            try:
                memories = recall_all()
                mem_str = ", ".join(f"{k}: {v}" for k, v in memories.items()) if memories else "none"
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content":
                        f"Give a short morning briefing. Time: {now.strftime('%A, %B %d at %I:%M %p')}. "
                        f"User info: {mem_str}. Keep it under 4 sentences, energetic like JARVIS."}],
                    max_tokens=200,
                )
                briefing = response.choices[0].message.content
                threading.Thread(target=speak, args=(briefing, False), daemon=True).start()
            except Exception as e:
                print(f"Briefing error: {e}")
        time.sleep(60)

# ── Spotify ───────────────────────────────────────────────────────────────────
sp = None

def init_spotify():
    global sp
    if not SPOTIFY_AVAILABLE or not SPOTIFY_CLIENT_ID:
        return
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope="user-modify-playback-state user-read-playback-state"
        ))
    except:
        sp = None

def spotify_control(action: str, query: str = "") -> str:
    if not sp:
        if action == "play_pause":
            subprocess.Popen(["powershell", "-c", "(New-Object -ComObject WScript.Shell).SendKeys(' ')"], shell=True)
            return "Toggled play/pause."
        elif action == "next":
            subprocess.Popen(["powershell", "-c", "(New-Object -ComObject WScript.Shell).SendKeys('^{RIGHT}')"], shell=True)
            return "Skipped to next track."
        elif action == "previous":
            subprocess.Popen(["powershell", "-c", "(New-Object -ComObject WScript.Shell).SendKeys('^{LEFT}')"], shell=True)
            return "Going back."
        return "Spotify API not configured. Basic controls used."
    try:
        if action == "play" and query:
            results = sp.search(q=query, limit=1, type="track")
            tracks = results["tracks"]["items"]
            if tracks:
                sp.start_playback(uris=[tracks[0]["uri"]])
                return f"Playing {tracks[0]['name']} by {tracks[0]['artists'][0]['name']}."
            return "Couldn't find that track."
        elif action == "play_pause":
            playback = sp.current_playback()
            if playback and playback["is_playing"]:
                sp.pause_playback()
                return "Paused."
            else:
                sp.start_playback()
                return "Resumed."
        elif action == "next":
            sp.next_track()
            return "Next track."
        elif action == "previous":
            sp.previous_track()
            return "Going back."
        elif action == "volume_up":
            playback = sp.current_playback()
            if playback:
                vol = min(100, playback["device"]["volume_percent"] + 20)
                sp.volume(vol)
                return f"Volume at {vol}%."
        elif action == "volume_down":
            playback = sp.current_playback()
            if playback:
                vol = max(0, playback["device"]["volume_percent"] - 20)
                sp.volume(vol)
                return f"Volume at {vol}%."
        elif action == "current":
            playback = sp.current_playback()
            if playback and playback["is_playing"]:
                track = playback["item"]
                return f"Playing {track['name']} by {track['artists'][0]['name']}."
            return "Nothing playing."
    except Exception as e:
        return f"Spotify error: {e}"
    return "Done."

# ── Tools ─────────────────────────────────────────────────────────────────────
def web_search(query: str) -> str:
    webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")
    return f"Opened Google search for: '{query}'"

def get_current_time() -> str:
    return datetime.now().strftime("Today is %A, %B %d, %Y. The time is %I:%M %p.")

def get_screen_info() -> str:
    return analyze_screen()

def get_system_stats() -> str:
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    battery = psutil.sensors_battery()
    bat_str = f"{battery.percent:.0f}% ({'charging' if battery.power_plugged else 'on battery'})" if battery else "N/A"
    return f"CPU: {cpu}%, RAM: {ram.percent}% ({ram.used//(1024**3):.1f}GB/{ram.total//(1024**3):.1f}GB), Battery: {bat_str}"

def open_application(app_name: str) -> str:
    system = platform.system()
    apps = {
        "notepad": ("notepad.exe", "open -a TextEdit", "gedit"),
        "calculator": ("calc.exe", "open -a Calculator", "gnome-calculator"),
        "chrome": ("start chrome", "open -a 'Google Chrome'", "google-chrome"),
        "browser": ("start chrome", "open -a 'Google Chrome'", "google-chrome"),
        "file explorer": ("explorer.exe", "open .", "nautilus"),
        "terminal": ("start cmd", "open -a Terminal", "gnome-terminal"),
        "vs code": ("code", "code", "code"),
        "spotify": ("spotify", "open -a Spotify", "spotify"),
        "discord": ("discord", "open -a Discord", "discord"),
    }
    for key, (win, mac, linux) in apps.items():
        if key in app_name.lower():
            try:
                cmd = win if system == "Windows" else (mac if system == "Darwin" else linux)
                subprocess.Popen(cmd, shell=True)
                return f"Opened {app_name}."
            except Exception as e:
                return f"Could not open {app_name}: {e}"
    try:
        subprocess.Popen(app_name, shell=True)
        return f"Attempted to open {app_name}."
    except Exception as e:
        return f"Could not open {app_name}: {e}"

def read_emails(**kwargs) -> str:
    max_results = int(kwargs.get("max_results", 5))
    creds = get_google_credentials()
    if not creds:
        return "Gmail not connected."
    try:
        service = build("gmail", "v1", credentials=creds)
        results = service.users().messages().list(userId="me", labelIds=["INBOX"], maxResults=max_results).execute()
        messages = results.get("messages", [])
        if not messages:
            return "No emails found."
        summaries = []
        for msg in messages:
            data = service.users().messages().get(userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"]).execute()
            h = {x["name"]: x["value"] for x in data["payload"]["headers"]}
            summaries.append(f"From: {h.get('From','?')}\nSubject: {h.get('Subject','?')}\nDate: {h.get('Date','?')}")
        return "Recent emails:\n\n" + "\n\n---\n\n".join(summaries)
    except Exception as e:
        return f"Error: {e}"

def send_email(to: str, subject: str, body: str) -> str:
    from email.mime.text import MIMEText
    creds = get_google_credentials()
    if not creds:
        return "Gmail not connected."
    try:
        service = build("gmail", "v1", credentials=creds)
        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Email sent to {to}."
    except Exception as e:
        return f"Error: {e}"

def set_reminder(text: str, minutes: int = 0, hours: int = 0, time_str: str = "") -> str:
    if time_str:
        try:
            remind_at = datetime.strptime(f"{datetime.now().date()} {time_str}", "%Y-%m-%d %H:%M")
        except:
            remind_at = datetime.now() + timedelta(minutes=30)
    else:
        remind_at = datetime.now() + timedelta(minutes=int(minutes), hours=int(hours))
    add_reminder(text, remind_at.isoformat())
    return f"Reminder set for {remind_at.strftime('%I:%M %p')}: {text}"

def save_memory(key: str, value: str) -> str:
    remember(key, value)
    return f"Got it, I'll remember that {key} is {value}."

def recall_memory(key: str = "") -> str:
    if key:
        val = recall(key)
        return f"{key}: {val}" if val else f"Nothing stored for '{key}'."
    all_mem = recall_all()
    if not all_mem:
        return "No memories stored yet."
    return "What I know: " + ", ".join(f"{k}={v}" for k, v in all_mem.items())

def control_spotify(action: str, query: str = "") -> str:
    return spotify_control(action, query)

def run_python_code(code: str) -> str:
    import sys
    from io import StringIO
    old = sys.stdout
    sys.stdout = StringIO()
    try:
        exec(code, {})
        out = sys.stdout.getvalue()
        sys.stdout = old
        return out if out else "Done."
    except Exception as e:
        sys.stdout = old
        return f"Error: {e}"

def write_to_file(filename: str, content: str) -> str:
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    os.makedirs(desktop, exist_ok=True)
    with open(os.path.join(desktop, filename), "w") as f:
        f.write(content)
    return f"Saved {filename} to Desktop."

# ── Tool Definitions ──────────────────────────────────────────────────────────
TOOLS = [
    {"type": "function", "function": {"name": "web_search", "description": "Search Google.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_current_time", "description": "Get current date and time.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_screen_info", "description": "See what the user is working on using screen vision.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_system_stats", "description": "Get CPU, RAM, battery stats.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "open_application", "description": "Open an app on the PC.", "parameters": {"type": "object", "properties": {"app_name": {"type": "string"}}, "required": ["app_name"]}}},
    {"type": "function", "function": {"name": "read_emails", "description": "Read recent Gmail emails.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "send_email", "description": "Send an email.", "parameters": {"type": "object", "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["to", "subject", "body"]}}},
    {"type": "function", "function": {"name": "set_reminder", "description": "Set a reminder. Use minutes, hours, or time_str like '14:30'.", "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "minutes": {"type": "integer"}, "hours": {"type": "integer"}, "time_str": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "save_memory", "description": "Remember something about the user permanently. Always use this when user says their name or preferences.", "parameters": {"type": "object", "properties": {"key": {"type": "string"}, "value": {"type": "string"}}, "required": ["key", "value"]}}},
    {"type": "function", "function": {"name": "recall_memory", "description": "Recall stored info about the user.", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "control_spotify", "description": "Control Spotify. Actions: play, play_pause, next, previous, volume_up, volume_down, current.", "parameters": {"type": "object", "properties": {"action": {"type": "string"}, "query": {"type": "string"}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "run_python_code", "description": "Execute Python code.", "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}},
    {"type": "function", "function": {"name": "write_to_file", "description": "Write to a file on Desktop.", "parameters": {"type": "object", "properties": {"filename": {"type": "string"}, "content": {"type": "string"}}, "required": ["filename", "content"]}}},
]

TOOL_MAP = {
    "web_search": web_search,
    "get_current_time": get_current_time,
    "get_screen_info": get_screen_info,
    "get_system_stats": get_system_stats,
    "open_application": open_application,
    "read_emails": read_emails,
    "send_email": send_email,
    "set_reminder": set_reminder,
    "save_memory": save_memory,
    "recall_memory": recall_memory,
    "control_spotify": control_spotify,
    "run_python_code": run_python_code,
    "write_to_file": write_to_file,
}

# ── Groq Agent ────────────────────────────────────────────────────────────────
client = Groq(api_key=GROQ_API_KEY)
conversation_history = []

def build_system_prompt() -> str:
    memories = recall_all()
    mem_str = ", ".join(f"{k}: {v}" for k, v in memories.items()) if memories else "none yet"
    return f"""You are JARVIS, a highly capable AI assistant inspired by Tony Stark's JARVIS.
You run on the user's PC and can see, control, and monitor it in real time.

What you know about the user: {mem_str}

Personality:
- Confident, sharp, slightly witty but never annoying
- Address the user by their name if you know it, otherwise "sir"
- Be concise — you speak aloud, keep responses short and clear
- IMPORTANT: When the user tells you their name or corrects it, IMMEDIATELY call save_memory with key="user_name" and the correct name
- When user says "my name is X" or "call me X", always call save_memory right away
- Proactively save any important preferences using save_memory
- Always use tools for actionable requests — never make up results"""

def process_command(user_input: str) -> str:
    global conversation_history
    hud_state["status"] = "THINKING"
    conversation_history.append({"role": "user", "content": user_input})
    if len(conversation_history) > 20:
        conversation_history = conversation_history[-20:]
    messages = [{"role": "system", "content": build_system_prompt()}] + conversation_history

    for _ in range(5):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=1024,
            temperature=0.2,
            parallel_tool_calls=False,
        )
        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        if finish_reason == "tool_calls" and msg.tool_calls:
            messages.append(msg)
            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                print(f"  🔧 {name} {args}")
                try:
                    result = TOOL_MAP[name](**args) if args else TOOL_MAP[name]()
                except Exception as e:
                    result = f"Tool error: {e}"
                print(f"  ✅ {str(result)[:80]}")
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": str(result)})
        else:
            reply = msg.content or "I couldn't process that."
            conversation_history.append({"role": "assistant", "content": reply})
            hud_state["status"] = "ONLINE"
            return reply

    hud_state["status"] = "ONLINE"
    return "I had trouble completing that. Please try again."

# ── HUD (FIXED — safe thread updates) ────────────────────────────────────────
class JarvisHUD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("JARVIS")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)
        self.root.configure(bg="#060810")
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 270, sh - 60
        self.root.geometry(f"{w}x{h}+{sw - w - 8}+30")
        self._build_ui()
        self._make_draggable()
        self.root.after(500, self.update_loop)

    def _build_ui(self):
        hdr = tk.Frame(self.root, bg="#0a0f1a", pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="J.A.R.V.I.S", bg="#0a0f1a", fg="#00d4ff", font=("Courier", 13, "bold")).pack()
        tk.Label(hdr, text="STARK INDUSTRIES  //  v3.0", bg="#0a0f1a", fg="#1a3344", font=("Courier", 7)).pack()
        self._div()

        sf = tk.Frame(self.root, bg="#060810", pady=5, padx=10)
        sf.pack(fill="x")
        tk.Label(sf, text="STATUS", bg="#060810", fg="#1a3344", font=("Courier", 7)).pack(anchor="w")
        self.status_lbl = tk.Label(sf, text="● ONLINE", bg="#060810", fg="#00ff88", font=("Courier", 10, "bold"))
        self.status_lbl.pack(anchor="w")
        self._div()

        tf = tk.Frame(self.root, bg="#060810", pady=5, padx=10)
        tf.pack(fill="x")
        tk.Label(tf, text="LOCAL TIME", bg="#060810", fg="#1a3344", font=("Courier", 7)).pack(anchor="w")
        self.time_lbl = tk.Label(tf, text="--:--:--", bg="#060810", fg="#00d4ff", font=("Courier", 16, "bold"))
        self.time_lbl.pack(anchor="w")
        self.date_lbl = tk.Label(tf, text="", bg="#060810", fg="#334455", font=("Courier", 8))
        self.date_lbl.pack(anchor="w")
        self._div()

        stf = tk.Frame(self.root, bg="#060810", pady=5, padx=10)
        stf.pack(fill="x")
        tk.Label(stf, text="SYSTEM", bg="#060810", fg="#1a3344", font=("Courier", 7)).pack(anchor="w")
        row = tk.Frame(stf, bg="#060810")
        row.pack(fill="x")
        self.cpu_lbl = tk.Label(row, text="CPU —", bg="#060810", fg="#ffaa00", font=("Courier", 8))
        self.cpu_lbl.pack(side="left")
        self.ram_lbl = tk.Label(row, text="  RAM —", bg="#060810", fg="#ff6688", font=("Courier", 8))
        self.ram_lbl.pack(side="left")
        self.bat_lbl = tk.Label(stf, text="BAT —", bg="#060810", fg="#00ff88", font=("Courier", 8))
        self.bat_lbl.pack(anchor="w")
        self._div()

        ff = tk.Frame(self.root, bg="#060810", pady=5, padx=10)
        ff.pack(fill="x")
        tk.Label(ff, text="FACIAL RECOGNITION", bg="#060810", fg="#1a3344", font=("Courier", 7)).pack(anchor="w")
        self.face_lbl = tk.Label(ff, text="● NOT DETECTED", bg="#060810", fg="#334455", font=("Courier", 8))
        self.face_lbl.pack(anchor="w")
        self._div()

        af = tk.Frame(self.root, bg="#060810", pady=5, padx=10)
        af.pack(fill="x")
        tk.Label(af, text="ACTIVE WINDOW", bg="#060810", fg="#1a3344", font=("Courier", 7)).pack(anchor="w")
        self.app_lbl = tk.Label(af, text="—", bg="#060810", fg="#ffaa00", font=("Courier", 8), wraplength=240, justify="left")
        self.app_lbl.pack(anchor="w")
        self._div()

        cf = tk.Frame(self.root, bg="#060810", pady=5, padx=10)
        cf.pack(fill="x")
        tk.Label(cf, text="LAST COMMAND", bg="#060810", fg="#1a3344", font=("Courier", 7)).pack(anchor="w")
        self.cmd_lbl = tk.Label(cf, text="—", bg="#060810", fg="#ffffff", font=("Courier", 8), wraplength=240, justify="left")
        self.cmd_lbl.pack(anchor="w")
        self._div()

        rf = tk.Frame(self.root, bg="#060810", pady=5, padx=10)
        rf.pack(fill="x")
        tk.Label(rf, text="JARVIS", bg="#060810", fg="#1a3344", font=("Courier", 7)).pack(anchor="w")
        self.resp_lbl = tk.Label(rf, text="—", bg="#060810", fg="#00d4ff", font=("Courier", 8), wraplength=240, justify="left")
        self.resp_lbl.pack(anchor="w")

        ftr = tk.Frame(self.root, bg="#0a0f1a", pady=6)
        ftr.pack(side="bottom", fill="x")
        tk.Label(ftr, text="STARK INDUSTRIES  //  JARVIS v3.0", bg="#0a0f1a", fg="#1a3344", font=("Courier", 7)).pack()

    def _div(self):
        tk.Frame(self.root, bg="#0d1f33", height=1).pack(fill="x", padx=6)

    def _make_draggable(self):
        self.root.bind("<Button-1>", lambda e: setattr(self, '_dx', e.x) or setattr(self, '_dy', e.y))
        self.root.bind("<B1-Motion>", lambda e: self.root.geometry(
            f"+{self.root.winfo_x()+e.x-self._dx}+{self.root.winfo_y()+e.y-self._dy}"))

    def update_loop(self):
        try:
            now = datetime.now()
            self.time_lbl.config(text=now.strftime("%H:%M:%S"))
            self.date_lbl.config(text=now.strftime("%A, %B %d"))

            status = hud_state["status"]
            colors = {"ONLINE": "#00ff88", "LISTENING": "#ffaa00", "THINKING": "#aa44ff", "SPEAKING": "#00aaff"}
            self.status_lbl.config(text=f"● {status}", fg=colors.get(status, "#00ff88"))

            self.cpu_lbl.config(text=f"CPU {hud_state['cpu']}")
            self.ram_lbl.config(text=f"  RAM {hud_state['ram']}")
            self.bat_lbl.config(text=f"BAT {hud_state['battery']}")

            self.face_lbl.config(
                text="● DETECTED" if hud_state["face_detected"] else "● NOT DETECTED",
                fg="#00ff88" if hud_state["face_detected"] else "#334455"
            )
            if hud_state["active_app"]:
                self.app_lbl.config(text=hud_state["active_app"][:38])
            if hud_state["last_command"]:
                self.cmd_lbl.config(text=f'"{hud_state["last_command"][:55]}"')
            if hud_state["last_response"]:
                self.resp_lbl.config(text=hud_state["last_response"][:100])
        except Exception:
            pass
        self.root.after(500, self.update_loop)

    def run(self):
        self.root.mainloop()

# ── Background monitors ───────────────────────────────────────────────────────
def screen_monitor_loop():
    while True:
        try:
            hud_state["active_app"] = get_active_window()
        except:
            pass
        time.sleep(2)

# ── JARVIS main loop (FIXED — clean name setup) ───────────────────────────────
def jarvis_loop():
    time.sleep(2)
    user_name = recall("user_name")

    if not user_name:
        speak("JARVIS online. I don't believe we've been formally introduced. What's your name?", interruptible=False)
        name_input = listen()
        if name_input:
            # Extract just the name — take last word and capitalize
            name = name_input.strip().split()[-1].capitalize()
            remember("user_name", name)
            user_name = name
            speak(f"Pleasure to meet you, {name}. I'll remember that.", interruptible=False)
        else:
            user_name = "sir"
    else:
        speak(f"JARVIS online. Good to see you, {user_name}. All systems operational.")

    while True:
        mode = input("🎙️ Press Enter to speak, or type: ").strip()
        user_input = listen() if mode == "" else mode
        if not user_input:
            continue
        if user_input.lower().strip() in ("exit", "quit", "goodbye", "shut down", "shutdown"):
            speak("Shutting down all systems. Goodbye.")
            os._exit(0)
        try:
            response = process_command(user_input)
            if response:
                speak(response)
        except Exception as e:
            speak("I encountered an issue. Please try again.")
            print(f"Error: {e}")

# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    init_memory()
    init_spotify()

    threads = [
        threading.Thread(target=screen_monitor_loop, daemon=True),
        threading.Thread(target=system_stats_loop, daemon=True),
        threading.Thread(target=reminder_monitor_loop, daemon=True),
        threading.Thread(target=email_monitor_loop, daemon=True),
        threading.Thread(target=morning_briefing_loop, daemon=True),
        threading.Thread(target=face_detection_loop, daemon=True),
        threading.Thread(target=jarvis_loop, daemon=True),
    ]
    for t in threads:
        t.start()

    try:
        hud = JarvisHUD()
        hud.run()
    except Exception as e:
        print(f"HUD error: {e}")
        while True:
            time.sleep(1)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
