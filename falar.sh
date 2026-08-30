#!/usr/bin/env bash
# falar.sh — liga/desliga o ditado por voz do Agente DERVS (português).
# Você fala, o texto é digitado na janela em foco. Silêncio não vira texto,
# então pode pausar e pensar. Rode de novo (ou clique 🎤) para parar.
VOICE_DIR="$HOME/voice"
PYTHON="$VOICE_DIR/.venv/bin/python"
ND="$VOICE_DIR/nerd-dictation/nerd-dictation"
MODEL="$VOICE_DIR/model"

# garante o daemon do ydotool ligado (necessário no Wayland p/ digitar)
if ! pgrep -x ydotoold >/dev/null 2>&1; then
  ydotoold >/dev/null 2>&1 &
  sleep 1
fi

if pgrep -f "nerd-dictation begin" >/dev/null 2>&1; then
  "$PYTHON" "$ND" end
  notify-send "DERVS" "🎤 microfone desligado" 2>/dev/null || echo "voz desligada"
else
  notify-send "DERVS" "🔴 ouvindo… fale à vontade" 2>/dev/null || echo "ouvindo..."
  "$PYTHON" "$ND" begin \
     --vosk-model-dir="$MODEL" \
     --simulate-input-tool=YDOTOOL \
     --continuous &
fi
