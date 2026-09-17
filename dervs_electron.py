#!/usr/bin/env python3
"""DERVS — ponto de entrada com a cara nova: o Electron em vez do Qt.

O processo Python continua dono de TUDO — trava de instância única, os
daemons (STT/voz), o cérebro, os trilhos de risco. A única coisa que muda é
quem desenha a tela: em vez do `Launcher`/`PopUp` do Qt (ver `dervs.py`,
bloco `__main__`), quem aparece agora é a janela do Electron, subida como
processo filho pela `PonteElectron` (`dervs_ponte_electron.py`).

A `PopUp` do Qt NÃO foi reescrita — ~1000 linhas corrigidas a duras penas
(fila de fala, porteiro, janela de desperto, STT via `QProcess`, cérebro,
plano, confirmação, execução, registro de queda) continuam intactas. A
classe `Motor` abaixo apenas HERDA `dervs.PopUp` e a usa como motor
INVISÍVEL: a janela Qt de verdade nunca é mostrada (nem `abrir()` nem
`show()` chamam o `QWidget.show()` de verdade); o que aparece na tela é
sempre a janela do Electron, e os poucos pontos onde a `PopUp` "fala com a
tela" (uma linha de conversa, o estado, o plano, o recado de erro) são
redirecionados para a ponte.

Decisão A do plano (`docs/superpowers/plans/dervs-cara-nova.md`, seção
"Decisões em aberto"): reusar a `PopUp` em vez de reescrever a orquestração
sem Qt. Custo: zero reescrita, os testes existentes de `dervs.py` continuam
valendo, e nenhuma correção do `ESTADO.md` é jogada fora.
"""
import os
import signal
import sys

from PyQt6 import QtWidgets

import dervs
import dervs_instancia as instancia
import dervs_registro as registro
import dervs_safety as seg
from dervs_ponte_electron import PonteElectron

CAMINHO_ELECTRON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "electron")

# ---- as quatro frases de erro de textos.md (seção "erros_e_avisos") -------
_CASO_SEM_SOM = ("Não chegou som nenhum. Fale mais perto do microfone, ou "
                  "confira se ele não está mudo.")
_CASO_MIC_DESCONECTADO = ("Não encontrei nenhum microfone ligado. Conecte um "
                           "na entrada rosa do computador — o DERVS volta a "
                           "ouvir sozinho, sem precisar reabrir nada.")
_CASO_AJUDANTE_CAIU = ("Uma parte do DERVS parou de responder. Feche e abra "
                        "o DERVS de novo pelo atalho da Área de Trabalho — "
                        "se continuar acontecendo, me avise.")
_CASO_SEM_INTERNET = ("Sem internet agora, e o DERVS precisa dela para "
                       "entender sua voz e decidir o que fazer. Confira sua "
                       "conexão e tente de novo assim que voltar.")
_APOIO_PADRAO = ("Isso costuma resolver na hora. Se insistir, feche e abra "
                  "o DERVS de novo.")


def _frase_do_recado(texto_interno: str):
    """Traduz o texto interno da `PopUp` (pensado para um tooltip Qt) para a
    frase de `textos.md` correspondente, e devolve `(frase, apoio)`.

    A `PopUp` hoje só produz o texto livre de `dervs_listen.motivo_do_silencio`
    (silêncio na escuta contínua) e algumas frases sobre o motor de
    transcrição (STT) cair/demorar/religar — nunca "sem internet" (não há,
    hoje, um caminho que chame `_recado_do_ouvido` por causa de rede; a
    frase existe aqui por completude do contrato e para o dia em que houver).
    Como a `PopUp` não expõe QUAL dos quatro casos é, a classificação é feita
    por palavra-chave no próprio texto — decisão tomada aqui por ambiguidade
    do plano (ver relato desta etapa).
    """
    t = (texto_interno or "").lower()
    if "nenhum microfone foi encontrado" in t:
        return (_CASO_MIC_DESCONECTADO, _APOIO_PADRAO)
    if t.startswith("nao entrou som") or t.startswith("não entrou som"):
        # inclui o caso em que o próprio `motivo_do_silencio()` especula
        # "mudo ... ou desconectado": a origem (som não chegou durante uma
        # escuta ativa) pesa mais que a especulação, e é o caso 1.
        return (_CASO_SEM_SOM, "")
    if "internet" in t:
        return (_CASO_SEM_INTERNET, _APOIO_PADRAO)
    return (_CASO_AJUDANTE_CAIU, _APOIO_PADRAO)


def _rotulo_do_passo(passo: dict) -> str:
    """Mesmo rótulo que `PopUp._confirmar_plano` monta para o campo de
    comando do cartão Qt — replicado aqui porque aquele é um closure local,
    não um método reaproveitável."""
    if passo.get("tipo") == "navegador":
        return "🌐 navegador: " + passo.get("objetivo", "")
    if passo.get("tipo") == "enriquecer":
        return "🔎 enriquecer (público): " + passo.get("dominio", "")
    return passo.get("comando", "")


def _nivel_ponte(nivel_interno: str) -> str:
    """O trilho de risco interno usa três nomes (`reversivel`, `muda_estado`,
    `destrutivo` — ver `dervs_safety.NIVEIS`); o contrato da ponte usa outros
    três (`reversivel`, `cuidado`, `destrutivo` — ver a seção "Contrato
    compartilhado" do plano). `muda_estado` vira `cuidado`."""
    if nivel_interno == "muda_estado":
        return "cuidado"
    if nivel_interno in ("reversivel", "destrutivo"):
        return nivel_interno
    return "reversivel"


def _nivel_do_passo(passo: dict) -> str:
    if passo.get("tipo") == "navegador":
        return "cuidado"      # dirige o Chrome logado do dono — nunca reversível
    if passo.get("tipo") == "enriquecer":
        return "reversivel"   # só fonte pública, não toca o alvo
    d = seg.decidir_risco(passo.get("comando", ""), passo.get("risco", "reversivel"))
    return _nivel_ponte(d["nivel"])


class Motor(dervs.PopUp):
    """A `PopUp` do Qt, herdada e NUNCA mostrada — o motor por trás da cara
    nova. Quem aparece na tela é sempre a janela do Electron; esta classe só
    redireciona para a `PonteElectron` os poucos pontos em que a `PopUp`
    "fala com a tela".
    """

    def __init__(self, ponte: PonteElectron):
        self.ponte = ponte
        self._ultimo_estado_enviado = None
        super().__init__()
        # Etapa 4: a `Voz` já sabe emitir o nível de amplitude enquanto fala,
        # se alguém ligar `ao_nivel`. Quem liga aqui é a ponte.
        self.voz.ao_nivel = ponte.enviar_volume

    # ---- a janela Qt de verdade NUNCA aparece --------------------------
    def abrir(self):
        self.ponte.enviar_mostrar()

    def show(self):
        self.ponte.enviar_mostrar()

    # ---- conversa, ocupado, recado de erro ------------------------------
    def _diz(self, papel, texto, cor=None):
        super()._diz(papel, texto, cor)
        self.ponte.enviar_fala(papel, texto or "")

    def _ocupado(self, on: bool, msg="pensando…"):
        super()._ocupado(on, msg)
        if on:
            self.ponte.enviar_estado("pensando", msg)
            self._ultimo_estado_enviado = "pensando"

    def _recado_do_ouvido(self, texto, cor):
        super()._recado_do_ouvido(texto, cor)
        frase, apoio = _frase_do_recado(texto)
        self.ponte.enviar_estado("erro", frase, apoio)
        self._ultimo_estado_enviado = "erro"

    # ---- microfone: a escuta contínua liga o nível na ponte -------------
    def alternar_conversa(self, ligar):
        super().alternar_conversa(ligar)
        if ligar and self.escuta is not None:
            self.escuta.nivel.connect(self.ponte.enviar_volume)

    # ---- plano: mostra e limpa o cartão ---------------------------------
    def _confirmar_plano(self):
        super()._confirmar_plano()
        if not self.plano:
            return
        passos = [{"rotulo": _rotulo_do_passo(p), "nivel": _nivel_do_passo(p)}
                  for p in self.plano]
        n = len(self.plano)
        pergunta = ("Vou fazer isto — dá um OK (ou diga 'ok') que eu executo:"
                    if n == 1 else
                    f"Vou fazer estes {n} passos — dá um OK (ou diga 'ok'):")
        self.ponte.enviar_plano(passos, _nivel_ponte(self._plano_nivel_max), pergunta)

    def cancelar_plano(self):
        super().cancelar_plano()
        self.ponte.enviar_plano([], "reversivel", "")

    def _processar_passo(self):
        super()._processar_passo()
        if not self.plano:
            # ou o plano acabou (passo_i chegou ao fim) ou nunca havia um —
            # nos dois casos o cartão, se estava aberto, tem de sumir.
            self.ponte.enviar_plano([], "reversivel", "")

    # ---- o relógio de 500ms que já existe --------------------------------
    def atualizar(self):
        super().atualizar()
        estado = self._estado_atual()
        if estado == self._ultimo_estado_enviado:
            return
        if estado == "erro" and self._recado_queda is not None:
            # Único caminho para "erro" que não passou por `_recado_do_ouvido`:
            # o aviso de queda anterior, montado direto no `__init__` da
            # `PopUp` antes de a ponte existir (`self._recado_queda = (...)`).
            texto, motivo = self._recado_queda
            self.ponte.enviar_estado("erro", texto, motivo)
        elif estado != "erro":
            # "erro" por causa de `_stt_recado` já foi mandado, com a frase
            # certa, por `_recado_do_ouvido` — não reenviar aqui sem texto.
            self.ponte.enviar_estado(estado)
        self._ultimo_estado_enviado = estado

    def _estado_atual(self) -> str:
        if self._recado_queda is not None or self._stt_recado is not None:
            return "erro"
        if self.voz.falando():
            return "falando"
        if self._tarefa is not None or self._transcrevendo:
            return "pensando"
        if self.escuta is not None:
            return "ouvindo"
        return "ocioso"


# ---- as peças do ponto de entrada, isoladas para dar para testar sem ------
# ---- subir um QApplication/Electron de verdade. ---------------------------

def _construir_me_chamaram(ponte: PonteElectron):
    """O que roda quando um segundo `dervs_electron.py` é chamado (clique no
    atalho com o DERVS já aberto). Roda numa thread de fundo — a do socket
    de instância única (`dervs_instancia.Posse._uma_conversa`).

    No Qt (`dervs.py`, classe `Ponte`) isto precisava atravessar para a
    thread da tela via `QTimer.singleShot`, porque mexer em widget fora da
    thread do Qt derruba o app — e um `QTimer` criado fora da thread da tela
    nunca dispara (comentário na própria `Ponte`). Aqui NÃO existe essa
    armadilha: a `PonteElectron` é thread-safe (escreve sob `threading.Lock`)
    e não toca em nenhum widget — só manda uma linha de JSON pelo `stdin` do
    Electron. Por isso a chamada é direta. Se um dia alguém achar que "falta"
    o padrão do `QTimer.singleShot` aqui, não falta: é proposital.
    """
    def _me_chamaram():
        ponte.enviar_mostrar()
    return _me_chamaram


def _construir_ao_plano(motor: Motor):
    """`confirmar` faz exatamente o que o botão "Confirmar e rodar" do Qt já
    fazia (`motor.confirmar_passo`, que por sua vez chama `confirmar_plano_ok`
    sozinho quando o que está pendente é o plano inteiro, não um passo) —
    não há necessidade de duplicar aqui a decisão de qual dos dois chamar."""
    def _ao_plano(resposta):
        if resposta == "confirmar":
            motor.confirmar_passo()
        elif resposta == "cancelar":
            motor.cancelar_plano()
    return _ao_plano


def _encerrar(motor: Motor, ponte: PonteElectron, posse):
    """O que o fechamento do app faz: desliga tudo o que a `PopUp` deixou de
    pé (`dervs.encerrar_tudo`, a mesma função de sempre — nada reescrito),
    fecha o processo do Electron, e libera a trava de instância única."""
    dervs.encerrar_tudo(motor)
    ponte.fechar()
    posse.soltar()


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    registro.colher_anterior()
    registro.instalar()
    dervs.faxina_de_audio(dervs.TMP)

    ponte_alvo = []      # preenchido depois que a ponte existe (ver abaixo)

    def _me_chamaram_ainda_nao_pronta():
        if ponte_alvo:
            ponte_alvo[0]()

    posse = instancia.tomar_posse(_me_chamaram_ainda_nao_pronta)
    if posse is None:
        sys.exit(0)          # já havia um DERVS aberto, e ele já foi avisado

    app = QtWidgets.QApplication([])
    app.setQuitOnLastWindowClosed(False)

    def _ao_sair():
        app.quit()            # o aboutToQuit chama `_encerrar`, ver abaixo

    # `ao_plano` precisa do `motor`, e o `motor` precisa da `ponte` — a mesma
    # indireção de `ponte_alvo` acima resolve a dependência circular sem
    # mexer em atributo privado da `PonteElectron`.
    ao_plano_alvo = []

    def _ao_plano_inicial(resposta):
        if ao_plano_alvo:
            ao_plano_alvo[0](resposta)

    ponte = PonteElectron(ao_sair=_ao_sair, ao_plano=_ao_plano_inicial, ao_pronto=lambda: None)
    motor = Motor(ponte)
    ao_plano_alvo.append(_construir_ao_plano(motor))
    ponte_alvo.append(_construir_me_chamaram(ponte))

    try:
        ponte.abrir(CAMINHO_ELECTRON)
    except FileNotFoundError as e:
        sys.stderr.write("dervs: %s\n" % e)
        sys.stderr.flush()
        dervs.encerrar_tudo(motor)
        posse.soltar()
        sys.exit(1)

    app.aboutToQuit.connect(lambda: _encerrar(motor, ponte, posse))
    app.exec()


if __name__ == "__main__":
    main()
