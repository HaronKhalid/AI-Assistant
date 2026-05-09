#!/bin/bash
# ============================================================
#  ARIA Voice Assistant — Auto Setup Script
#  Ubuntu / Debian — CPU Only — 16GB RAM
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

print_step() { echo -e "\n${CYAN}${BOLD}[STEP]${NC} $1"; }
print_ok()   { echo -e "${GREEN}✓${NC} $1"; }
print_warn() { echo -e "${YELLOW}⚠${NC}  $1"; }
print_err()  { echo -e "${RED}✗${NC}  $1"; }

echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║     ARIA Voice Assistant Setup       ║"
echo "  ║     Linux · CPU · 16GB RAM           ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"

# ── 1. System packages ──────────────────────────────────────
print_step "Installing system dependencies..."
sudo apt-get update -q
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    portaudio19-dev python3-pyaudio \
    ffmpeg \
    curl wget git \
    espeak-ng \
    alsa-utils pulseaudio \
    build-essential
print_ok "System packages installed"

# ── 2. Python virtual environment ───────────────────────────
print_step "Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
print_ok "Virtual environment ready at ./venv"

# ── 3. Python packages ──────────────────────────────────────
print_step "Installing Python packages (this may take a few minutes)..."
pip install -q \
    openai-whisper \
    sounddevice \
    pyaudio \
    numpy \
    scipy \
    requests \
    pyyaml \
    colorlog \
    pydub \
    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu \
    silero-vad \
    openwakeword \
    ollama \
    rich
print_ok "Python packages installed"

# ── 4. Piper TTS ─────────────────────────────────────────────
print_step "Installing Piper TTS..."
mkdir -p models/piper
cd models/piper

PIPER_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"
wget -q --show-progress "$PIPER_URL" -O piper.tar.gz
tar -xzf piper.tar.gz
rm piper.tar.gz

# Download a high-quality English voice
VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
VOICE_CONFIG_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"
wget -q --show-progress "$VOICE_URL" -O en_US-lessac-medium.onnx
wget -q --show-progress "$VOICE_CONFIG_URL" -O en_US-lessac-medium.onnx.json

cd ../..
print_ok "Piper TTS installed with en_US-lessac voice"

# ── 5. Whisper model (base — good balance for CPU) ───────────
print_step "Pre-downloading Whisper 'base' model..."
python3 -c "import whisper; whisper.load_model('base')"
print_ok "Whisper base model downloaded"

# ── 6. Ollama ────────────────────────────────────────────────
print_step "Installing Ollama..."
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
    print_ok "Ollama installed"
else
    print_warn "Ollama already installed, skipping"
fi

print_step "Pulling Mistral 7B model (this is ~4GB, will take a while)..."
print_warn "Make sure you have a stable internet connection"
ollama pull mistral
print_ok "Mistral 7B ready"

# ── 7. OpenWakeWord model ────────────────────────────────────
print_step "Downloading OpenWakeWord models..."
python3 -c "
import openwakeword
openwakeword.utils.download_models()
print('OpenWakeWord models downloaded')
"
print_ok "Wake word models ready"

# ── 8. Create directories ────────────────────────────────────
print_step "Creating project directories..."
mkdir -p logs models/whisper

# ── Done ─────────────────────────────────────────────────────
echo -e "\n${GREEN}${BOLD}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║         Setup Complete! ✓            ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  Run the assistant with:"
echo -e "  ${BOLD}source venv/bin/activate && python main.py${NC}"
echo ""
