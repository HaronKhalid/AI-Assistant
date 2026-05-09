# 🎙️ ARIA — Open Source Voice Assistant
### Built for Linux · CPU-Optimized · Fully Offline

---

## Stack
- **Wake Word**: OpenWakeWord
- **STT**: OpenAI Whisper (base model, CPU)
- **Brain**: Ollama + Mistral 7B
- **TTS**: Piper TTS
- **VAD**: Silero VAD
- **Skills**: Python modules

## Quick Start
```bash
chmod +x setup.sh && ./setup.sh
python main.py
```

## Project Structure
```
voice-assistant/
├── main.py                  # Entry point
├── setup.sh                 # Auto-installer
├── requirements.txt
├── config/
│   └── settings.yaml        # All configuration
├── core/
│   ├── wake_word.py         # Wake word detection
│   ├── stt.py               # Speech to text
│   ├── tts.py               # Text to speech
│   ├── brain.py             # LLM reasoning
│   ├── vad.py               # Voice activity detection
│   └── router.py            # Intent routing
├── skills/
│   ├── __init__.py
│   ├── timer.py
│   ├── weather.py
│   ├── system_control.py
│   ├── web_search.py
│   └── general.py
├── models/                  # Auto-downloaded models
└── logs/
```
