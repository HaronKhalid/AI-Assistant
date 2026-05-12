# ARIA — Open Source Voice Assistant
**Built for Linux · CPU-Optimized · Fully Offline · Privacy-First**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python](https://img.shields.io/badge/Python-58.9%25-3776ab?logo=python&logoColor=white)
![HTML](https://img.shields.io/badge/HTML-38.5%25-e34c26?logo=html5&logoColor=white)
![Shell](https://img.shields.io/badge/Shell-2.6%25-4eaa25?logo=gnu-bash&logoColor=white)

---

## 🎯 Overview

ARIA is a lightweight, fully offline voice assistant designed to run on CPU-constrained systems. It combines state-of-the-art open-source models for speech recognition, natural language understanding, and text-to-speech synthesis—all without cloud dependencies.

**Key Features:**
- 🔇 **Fully Offline** – No cloud API calls or internet required
- ⚡ **CPU-Optimized** – Runs efficiently on modest hardware
- 🔒 **Privacy-First** – Your voice and data stay local
- 🛠️ **Extensible** – Easy-to-add custom skills
- 🚀 **Quick Setup** – Automated installation script
- 🐧 **Linux Native** – Optimized for Linux environments

---

## 📦 Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Wake Word Detection** | [OpenWakeWord](https://github.com/openwakeword/openwakeword) | Always-listening wake word detection |
| **Speech-to-Text** | [OpenAI Whisper](https://github.com/openai/whisper) (base model) | CPU-friendly speech recognition |
| **Language Model** | [Ollama](https://ollama.ai) + [Mistral 7B](https://mistral.ai) | Reasoning and intent understanding |
| **Text-to-Speech** | [Piper TTS](https://github.com/rhasspy/piper) | Natural voice synthesis |
| **Voice Activity Detection** | [Silero VAD](https://github.com/snakers4/silero-vad) | Efficient speech endpoint detection |
| **Skills Framework** | Python modules | Extensible task execution |

---

## 🚀 Quick Start

### Prerequisites
- Linux (Ubuntu 20.04+ recommended)
- Python 3.8+
- ~2GB free disk space

### Installation

```bash
# Clone the repository
git clone https://github.com/HaroonKhalidA/AI-Assistant.git
cd AI-Assistant
```

# Run automated setup
chmod +x setup.sh
./setup.sh

# Start the assistant
python main.py

That's it! The setup script handles all dependencies, model downloads, and configuration.
📁 Project Structure
Code

```
AI-Assistant/
├── main.py                      # Application entry point
├── setup.sh                     # Automated installation & setup
├── requirements.txt             # Python dependencies
│
├── config/
│   └── settings.yaml            # Global configuration (models, API keys, features)
│
├── core/                        # Core voice processing pipeline
│   ├── wake_word.py            # Wake word detection engine
│   ├── stt.py                  # Speech-to-text processor
│   ├── tts.py                  # Text-to-speech synthesizer
│   ├── brain.py                # LLM reasoning engine
│   ├── vad.py                  # Voice activity detection
│   └── router.py               # Intent routing & skill dispatcher
│
├── skills/                      # Extensible skill modules
│   ├── __init__.py
│   ├── timer.py                # Timer & alarm functionality
│   ├── weather.py              # Weather information (offline fallback)
│   ├── system_control.py       # System commands (volume, brightness, etc.)
│   ├── web_search.py           # Local search capabilities
│   └── general.py              # General conversation
│
├── models/                      # Auto-downloaded ML models (gitignored)
├── logs/                        # Application logs
└── README.md                    # This file
```

⚙️ Configuration

Edit config/settings.yaml to customize:
YAML

# Wake word
wake_word: "hey aria"
sensitivity: 0.5

# Model selection
stt_model: "base"           # whisper model size
tts_voice: "en_US"         # TTS voice
brain_model: "mistral"     # Local LLM

# Features
enable_vad: true
enable_web_search: false
log_level: "INFO"

🎤 Usage
Start ARIA
bash

python main.py

Voice Commands

    Wake word: "Hey ARIA"
    Examples:
        "What's the weather?"
        "Set a timer for 10 minutes"
        "Control my system brightness"
        "Tell me about Python"

Command Line Options
bash

python main.py --config custom_config.yaml    # Use custom config
python main.py --debug                        # Enable debug logging
python main.py --offline                      # Force offline mode

🛠️ Extending with Custom Skills

Create a new skill in skills/ directory:
Python

# skills/my_skill.py

class MySkill:
    def __init__(self):
        self.name = "my_skill"
        self.keywords = ["keyword1", "keyword2"]
    
    def execute(self, text: str) -> str:
        """Process the user request and return response"""
        return "Response to user"
    
    def is_applicable(self, text: str) -> bool:
        """Determine if this skill should handle the request"""
        return any(kw in text.lower() for kw in self.keywords)

Then register in router.py:
Python

from skills.my_skill import MySkill
self.skills.append(MySkill())

📊 Performance Metrics
Metric	Value
Wake word detection latency	< 100ms
Speech-to-text processing	~5-10s for 10s audio
LLM response generation	2-5s (Mistral 7B, CPU)
Total pipeline latency	~10-20s end-to-end
Memory footprint	~1.5GB (base model)

Metrics vary based on hardware and model configuration
🐛 Troubleshooting
Audio input not detected
bash

# List available audio devices
arecord -l

# Update config to use correct device

Slow responses

    Reduce model size in settings (e.g., tiny for Whisper)
    Lower sensitivity for faster wake word detection
    Disable unnecessary skills

Model download fails
bash

# Manually download models
python -m pip install ollama
ollama pull mistral

📚 Dependencies

Key Python packages:

    openai-whisper – Speech recognition
    piper-tts – Text-to-speech
    openWakeWord – Wake word detection
    silero-vad – Voice activity detection
    pyyaml – Configuration management

See requirements.txt for complete list.
🤝 Contributing

Contributions are welcome! Please:

    Fork the repository
    Create a feature branch (git checkout -b feature/amazing-feature)
    Commit your changes (git commit -m 'Add amazing feature')
    Push to the branch (git push origin feature/amazing-feature)
    Open a Pull Request

📝 License

This project is licensed under the MIT License – see the LICENSE file for details.
📞 Support & Resources

    Issues & Bugs: GitHub Issues
    Discussions: GitHub Discussions
    Documentation: Check the docs/ directory for detailed guides

🙏 Acknowledgments

Built with love using:

    OpenWakeWord by Tend
    Whisper by OpenAI
    Ollama for local LLM serving
    Piper by Rhasspy
    Silero VAD by Snakers4

