#!/usr/bin/env bash
# Liga a digitacao por voz no Wayland. Precisa de senha UMA vez.
# Grava tudo em log para o Claude conferir depois.
LOG="$HOME/voice/ligar-voz.log"
{
  echo "=== INICIO $(date) ==="
  sudo apt-get update
  sudo apt-get install -y ydotool wtype
  # permissao de /dev/uinput para o usuario (sem isso o ydotool nao digita)
  echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' \
    | sudo tee /etc/udev/rules.d/80-uinput.rules
  sudo groupadd -f input
  sudo usermod -aG input "$USER"
  sudo modprobe uinput
  sudo udevadm control --reload-rules && sudo udevadm trigger
  echo "=== FIM (codigo $?) ==="
} 2>&1 | tee "$LOG"
echo
echo ">>> PRONTO. IMPORTANTE: saia e entre na sessao (logout/login) uma vez,"
echo "    para o grupo 'input' valer. Depois volte ao Claude e diga: voz pronta <<<"
