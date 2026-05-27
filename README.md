# J.A.R.V.I.S
### Just A Rather Very Intelligent System

> *"Sometimes you gotta run before you can walk."* — Tony Stark

A fully local, voice-controlled AI assistant inspired by Tony Stark's JARVIS from the Iron Man films. Built with Python, powered by Groq AI, and running entirely on your PC.

---

## 🎬 Demo

> JARVIS comes online, greets you by name, monitors your screen, reads your emails, controls your music, and responds to your voice — all in real time.

---

## ✨ Features

### 🎙️ Voice & Text Interface
- Speak or type commands naturally
- Male TTS voice output
- Press Enter anytime to interrupt JARVIS mid-speech

### 🧠 AI Brain (Groq)
- Powered by `meta-llama/llama-4-scout-17b` via Groq API
- Fast, free, and reliable tool calling
- Maintains conversation context across commands

### 👁️ Screen Awareness
- JARVIS can see what you're working on
- Ask *"what am I looking at?"* and get a real answer
- Active window tracked live on the HUD

### 😄 Face Detection
- Webcam watches for your face
- Greets you when you sit down
- 5-minute cooldown prevents repeated greetings

### 🧠 Persistent Memory
- Remembers your name, preferences, and important info
- Stored locally in SQLite — never in the cloud
- Correct it anytime and it updates immediately

### 📧 Gmail Integration
- Read your latest emails by voice
- Send emails hands-free
- Proactive alerts for new emails every 5 minutes

### 🎵 Spotify Control
- Play any song by name
- Pause, skip, volume control by voice
- No Spotify API key required

### ⏰ Reminders
- *"Remind me in 30 minutes to drink water"*
- *"Remind me at 3pm to call mom"*
- JARVIS speaks the reminder when time's up

### 🌅 Morning Briefing
- Every morning at 8 AM JARVIS briefs you
- Personalized based on what it knows about you

### 🔋 System Stats
- Live CPU, RAM, and battery on the HUD
- Ask *"how is my system doing?"* anytime

### 🖥️ Floating HUD Overlay
- Always-on-top panel docked to your screen
- Shows status, time, last command, last response
- Drag it anywhere — Iron Man style

### 💻 PC Control
- Open any application by voice
- Run Python code on the fly
- Write and save files to your Desktop

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| AI Brain | Groq API (llama-4-scout-17b) |
| Voice Input | SpeechRecognition + sounddevice |
| Voice Output | pyttsx3 (offline TTS) |
| Face Detection | OpenCV (haarcascade) |
| Screen Vision | Pillow + Groq Vision |
| Gmail & Calendar | Google API Python Client |
| Memory | SQLite3 |
| HUD | Tkinter |
| Music | Spotify URI + keyboard shortcuts |
| System Stats | psutil |

---

## ⚡ Quick Setup

### 1. Clone the repo
```bash
git clone https://github.com/Havishk2911/JARVIS.git
cd JARVIS
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Get your free Groq API key
- Sign up at [console.groq.com](https://console.groq.com)
- Create an API key
- Paste it in `jarvis.py`:
```python
GROQ_API_KEY = "your-key-here"
```

### 4. Gmail setup (optional)
- Enable Gmail API at [console.cloud.google.com](https://console.cloud.google.com)
- Download `credentials.json` and place it in the project folder
- First run will open a browser to authorize

### 5. Run JARVIS
```bash
python jarvis.py
```

JARVIS will ask your name on first run and remember it forever.

---

## 🎤 Example Commands

| You say | JARVIS does |
|---|---|
| *"What time is it?"* | Tells you the current time |
| *"Read my emails"* | Reads your latest Gmail inbox |
| *"Send an email to john@gmail.com"* | Drafts and sends the email |
| *"Play Blinding Lights on Spotify"* | Opens Spotify search |
| *"What am I working on?"* | Analyzes your screen |
| *"How's my system?"* | Reports CPU, RAM, battery |
| *"Remind me in 20 minutes to eat"* | Sets a voice reminder |
| *"Open VS Code"* | Launches VS Code |
| *"Search for latest AI news"* | Opens Google search |
| *"Remember that I prefer dark mode"* | Saves to memory permanently |

---

## 📁 Project Structure

```
JARVIS/
├── jarvis.py          # Main agent
├── requirements.txt   # Dependencies
├── README.md          # This file
├── .gitignore         # Keeps secrets safe
└── credentials.json   # (you add this — not in repo)
```

---

## 🔒 Privacy & Security

- All AI processing is done via Groq's API — no data stored on their servers beyond the request
- Gmail credentials never leave your PC
- Memory database is stored locally only
- Never commit `credentials.json` or `token.pickle` to GitHub

---

## 🗺️ Roadmap

- [x] Voice input + output
- [x] Groq AI brain with tool calling
- [x] Gmail integration
- [x] Floating HUD overlay
- [x] Face detection & greeting
- [x] Persistent memory
- [x] Screen awareness
- [x] Morning briefing
- [x] Spotify control
- [x] System stats
- [ ] Double clap wake word
- [ ] Proactive calendar alerts
- [ ] WhatsApp integration (when API allows)
- [ ] Custom wake word training

---

## 🙏 Credits

Built with:
- [Groq](https://groq.com) — blazing fast LLM inference
- [OpenCV](https://opencv.org) — face detection
- [Google APIs](https://developers.google.com) — Gmail
- [Anthropic Claude](https://claude.ai) — helped build this 🤖

---

## ⚠️ Disclaimer

This project is for personal productivity use only. Keep your API keys private and never commit them to GitHub.

---

<p align="center">
  Built with ❤️ | Inspired by Tony Stark
</p>
