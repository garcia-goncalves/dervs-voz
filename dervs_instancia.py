#!/usr/bin/env python3
"""Garante que existe UM DERVS só — e faz o segundo clique no ícone TRAZER
o que já está aberto, em vez de abrir outro por cima.

Por que existe: em 02/09/2026 o dono disse "o DERVS sumiu / bugou". Medido:
clicar duas vezes no ícone deixava DOIS DERVS vivos, empilhados exatamente no
mesmo ponto da tela, disputando o microfone; o de cima comia o clique do de
baixo. E o menu da bandeja não tinha "Sair", então não havia como fechar
nenhum sem o Gerenciador de Tarefas — que o dono não usa. O app piorava a cada
uso, para sempre.

Como funciona: quem abre primeiro reserva uma porta no PRÓPRIO computador
(127.0.0.1, nunca a rede) e anota o número num arquivo, junto do número do
processo e de uma senha sorteada na hora. Quem abrir depois lê o arquivo,
confere que aquele processo ainda está vivo, bate na porta com a senha, o
primeiro aparece na tela, e o segundo encerra sem subir.

Duas travas que parecem detalhe e não são:

* a resposta tem de ser EXATAMENTE `DERVS-OK`. Uma porta abandonada por um
  DERVS morto pode ser reaproveitada pelo Windows para qualquer outro programa
  local, e um servidor web qualquer responde "HTTP/1.1 200 OK" — bastava
  procurar "OK" solto para o DERVS achar que já estava aberto e se recusar a
  abrir PARA SEMPRE, calado. Que é exatamente o defeito que este arquivo veio
  consertar;
* instância única é conveniência, não pré-requisito. Se a reserva falhar por
  motivo de máquina (pasta sem permissão, disco cheio, firewall), o DERVS ABRE
  do mesmo jeito, sem trava — melhor um app sem trava que nenhum app.
"""
import os
import sys
import json
import socket
import secrets
import threading

import dervs_config as cfg

# Ao lado da configuração: %APPDATA%\dervs no Windows, ~/.config/dervs no Linux.
CAMINHO_PADRAO = os.path.join(cfg.CONFIG_DIR, "instancia.json")

ENDERECO = "127.0.0.1"       # só este computador. Nunca 0.0.0.0.
PEDIDO = "MOSTRAR"
RESPOSTA_SIM = b"DERVS-OK"   # exata, e nossa: nenhum outro servidor responde isto
RESPOSTA_NAO = b"DERVS-NAO"
_LIMITE_LINHA = 200          # senha + verbo cabem de sobra; o resto é lixo
_ESPERA_SEG = 1.5            # o que o segundo processo espera por resposta
_ESPERA_ATENDER = 0.3        # o que o atendente espera por um pedido, por conexão


def _processo_vivo(pid) -> bool:
    """Aquele processo ainda existe? Registro de DERVS morto não vale nada.

    Sem isto, um registro deixado para trás por uma queda apontava para uma
    porta que o Windows podia já ter dado a OUTRO programa — e a conversa com
    esse estranho é que decidia se o DERVS abria ou não.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k = ctypes.windll.kernel32
        h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        k.CloseHandle(h)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _ler_registro(caminho: str):
    """Devolve {"porta", "senha", "pid"} do DERVS que abriu antes, ou None.

    Arquivo faltando, ilegível, torto ou de um processo já morto vira None em
    silêncio: nada disso pode ser o motivo de o DERVS nunca mais abrir.
    """
    try:
        with open(caminho, encoding="utf-8") as f:
            dado = json.load(f)
        porta = int(dado["porta"])
        senha = str(dado["senha"])
        pid = dado.get("pid")
    except (OSError, ValueError, TypeError, KeyError):
        return None
    if not (0 < porta < 65536) or not senha:
        return None
    if pid is not None and not _processo_vivo(pid):
        return None
    return {"porta": porta, "senha": senha, "pid": pid}


def chamar_quem_ja_esta_aberto(caminho: str = CAMINHO_PADRAO,
                               espera: float = _ESPERA_SEG) -> bool:
    """Pede ao DERVS que já está aberto para aparecer. Diz se ELE atendeu.

    False = não tem DERVS nenhum vivo lá; quem chamou pode subir.
    """
    reg = _ler_registro(caminho)
    if reg is None:
        return False
    try:
        with socket.create_connection((ENDERECO, reg["porta"]), timeout=espera) as s:
            s.settimeout(espera)
            s.sendall((PEDIDO + " " + reg["senha"] + "\n").encode())
            # Comparação EXATA e com verbo nosso: ver o cabeçalho deste arquivo.
            return s.recv(64).strip() == RESPOSTA_SIM
    except OSError:
        return False


class Posse:
    """A reserva do único DERVS. Enquanto ela existe, ninguém mais sobe."""

    def __init__(self, caminho: str, ao_ser_chamado):
        self.caminho = caminho
        self._ao_ser_chamado = ao_ser_chamado
        self._senha = secrets.token_urlsafe(24)
        self._tomada = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tomada.bind((ENDERECO, 0))       # 0 = o sistema escolhe uma livre
        self._tomada.listen(8)
        self.endereco, self.porta = self._tomada.getsockname()
        self._parar = threading.Event()
        self._atendente = threading.Thread(target=self._atender, daemon=True)
        self._atendente.start()
        self._anotar()

    # ---- registro em disco ----
    def _anotar(self):
        """Grava porta, senha e pid, trocando o arquivo de uma vez só
        (os.replace), para nunca existir um registro pela metade.

        O arquivo nasce 0600. No Windows a ACL herdada de %APPDATA% já basta;
        no Linux, sem isto, a senha ficaria legível por qualquer conta da
        máquina — que é justamente de quem a senha deveria proteger.
        """
        os.makedirs(os.path.dirname(self.caminho) or ".", exist_ok=True)
        temporario = self.caminho + ".tmp"
        fd = os.open(temporario, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"porta": self.porta, "senha": self._senha,
                       "pid": os.getpid()}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporario, self.caminho)

    # ---- atendimento ----
    def _atender(self):
        """Aceita conexões e entrega CADA UMA a uma thread curta.

        Atender em série deixava a trava furada: bastava um programa qualquer
        da máquina abrir conexões e ficar calado para segurar a fila, o clique
        de verdade estourar o tempo, e um SEGUNDO DERVS subir inteiro — o bug
        que este arquivo existe para impedir.
        """
        while not self._parar.is_set():
            try:
                conversa, _ = self._tomada.accept()
            except OSError:
                return                      # a tomada fechou: hora de sair
            threading.Thread(target=self._uma_conversa, args=(conversa,),
                             daemon=True).start()

    def _uma_conversa(self, conversa):
        certo = False
        with conversa:
            try:
                conversa.settimeout(_ESPERA_ATENDER)
                linha = conversa.recv(_LIMITE_LINHA).decode("utf-8", "replace")
                certo = linha.strip() == PEDIDO + " " + self._senha
                conversa.sendall((RESPOSTA_SIM if certo else RESPOSTA_NAO) + b"\n")
            except OSError:
                return
        if not certo or self._parar.is_set():
            return
        # Fora do `with`: mostrar a janela pode demorar, e a resposta já foi.
        try:
            self._ao_ser_chamado()
        except Exception:
            # A tela explodir não pode deixar o DERVS surdo ao próximo clique —
            # é justamente aí que o dono mais precisa dele.
            pass

    # ---- fim ----
    def soltar(self):
        """Libera a vez para o próximo DERVS. Seguro chamar duas vezes."""
        self._parar.set()
        try:
            self._tomada.close()
        except OSError:
            pass
        # Só apaga o registro se ele ainda for NOSSO: numa corrida, apagar o de
        # outra instância a deixaria viva e inalcançável.
        reg = _ler_registro(self.caminho)
        if reg is None or reg.get("pid") == os.getpid():
            for caminho in (self.caminho, self.caminho + ".tmp"):
                try:
                    os.remove(caminho)
                except OSError:
                    pass


class SemTrava:
    """O que devolvemos quando a reserva falhou por motivo de MÁQUINA.

    Instância única é conveniência; o app é o essencial. Pasta sem permissão,
    disco cheio ou firewall barrando o loopback não podem impedir o DERVS de
    abrir — e muito menos em silêncio, que é a família de defeito que esta peça
    veio consertar.
    """
    porta = None
    endereco = None

    def __init__(self, motivo=""):
        self.motivo = motivo

    def soltar(self):
        pass


def tomar_posse(ao_ser_chamado, caminho: str = CAMINHO_PADRAO):
    """Diz se este DERVS pode subir, e devolve a reserva.

    * `Posse`    — é o único DERVS: pode subir, e a trava está de pé;
    * `SemTrava` — pode subir, mas SEM trava (a reserva falhou na máquina);
    * `None`     — já havia um DERVS aberto, que JÁ FOI avisado para aparecer.
                   Quem chamou só precisa encerrar caladamente.

    `ao_ser_chamado` roda numa thread de fundo. Quem usa Qt tem de pular para a
    thread da tela antes de mexer em janela.
    """
    if chamar_quem_ja_esta_aberto(caminho):
        return None
    try:
        return Posse(caminho, ao_ser_chamado)
    except OSError as e:
        return SemTrava(str(e))
