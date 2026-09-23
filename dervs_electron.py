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
import threading

from PyQt6 import QtCore, QtWidgets

import dervs
import dervs_config as config
import dervs_instancia as instancia
import dervs_registro as registro
import dervs_safety as seg
import dervs_sistema as sistema
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

    # O botão do HUD chega pela thread de leitura da ponte. Emitir um sinal
    # daqui atravessa sozinho para a thread da tela (o Motor mora nela) —
    # mexer em `b_conversa`/`Escuta` de outra thread derruba o app, e um
    # `QTimer` criado fora da thread do Qt nunca dispara (ver `dervs.Ponte`).
    _pedido_microfone = QtCore.pyqtSignal(bool)

    def __init__(self, ponte: PonteElectron):
        self.ponte = ponte
        self._ultimo_estado_enviado = None
        self._ultimo_microfone_enviado = None
        # Identidade do cartão em trânsito (correção de concorrência — ver
        # relato desta etapa): sem isto, uma resposta duplicada ou atrasada
        # do Electron (duplo-clique cujas duas mensagens saem antes do
        # cartão anterior sumir da tela) não tem como saber a qual cartão se
        # refere. Contador incremental — suficiente aqui porque o único uso
        # é descartar resposta desatualizada, não segurança criptográfica.
        self._proximo_cartao_id = 0
        self._cartao_pendente = None
        super().__init__()
        # Etapa 4: a `Voz` já sabe emitir o nível de amplitude enquanto fala,
        # se alguém ligar `ao_nivel`. Quem liga aqui é a ponte.
        self.voz.ao_nivel = ponte.enviar_volume
        self._pedido_microfone.connect(self._microfone_na_tela)

    # ---- microfone: o liga/desliga do HUD --------------------------------
    def pedir_microfone(self, ligar: bool):
        """Seguro de chamar de qualquer thread (ver `_pedido_microfone`)."""
        self._pedido_microfone.emit(bool(ligar))

    def _microfone_na_tela(self, ligar: bool):
        # o mesmo caminho do botão Qt antigo: `toggled` → `alternar_conversa`,
        # que grava `escuta_ao_abrir` e abre/fecha a `Escuta`.
        self.b_conversa.setChecked(ligar)

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

    # ---- identidade do cartão em trânsito --------------------------------
    def _novo_cartao_id(self) -> int:
        """Um id novo por cartão enviado que espera resposta — guardado em
        `self._cartao_pendente` para `_confirmar_do_electron` descartar
        resposta desatualizada (ver relato desta etapa)."""
        self._proximo_cartao_id += 1
        self._cartao_pendente = self._proximo_cartao_id
        return self._proximo_cartao_id

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
        cartao_id = self._novo_cartao_id()
        self.ponte.enviar_plano(passos, _nivel_ponte(self._plano_nivel_max),
                                 pergunta, cartao_id=cartao_id)

    def cancelar_plano(self):
        super().cancelar_plano()
        self.ponte.enviar_plano([], "reversivel", "")

    def confirmar_plano_ok(self, por_voz=False):
        aguardando_antes = self._aguardando_ok
        super().confirmar_plano_ok(por_voz)
        if aguardando_antes and not self._aguardando_ok:
            # o Qt já escondeu a barra aqui (`self.barra.hide()`, dentro do
            # `confirmar_plano_ok` original) — sem isto o cartão do plano
            # inteiro fica preso na tela do Electron até o próximo passo
            # destrutivo (ou o fim do plano) mandar um cartão novo por cima.
            self.ponte.enviar_plano([], "reversivel", "")

    def _processar_passo(self):
        super()._processar_passo()
        if not self.plano:
            # ou o plano acabou (passo_i chegou ao fim) ou nunca havia um —
            # nos dois casos o cartão, se estava aberto, tem de sumir.
            self.ponte.enviar_plano([], "reversivel", "")

    # ---- passo destrutivo: o cartão de risco também precisa ir pela ponte ----
    # BUG DE SEGURANÇA corrigido aqui: `_mostrar_cartao` (herdado de `PopUp`,
    # `dervs.py:1345`) só escrevia nos widgets Qt escondidos — o Electron
    # nunca era avisado, o dono nunca via o cartão, e o plano travava em
    # silêncio no primeiro passo destrutivo. Ver relato desta etapa.
    def _mostrar_cartao(self, passo, d):
        super()._mostrar_cartao(passo, d)     # mantém o Qt invisível intacto
        self._enviar_cartao_do_passo(passo, d, segunda_vez=False)

    def _enviar_cartao_do_passo(self, passo, d, segunda_vez: bool):
        """Extensão do contrato da ponte (ver `dervs_ponte_electron.py`,
        cabeçalho "Verbos Python → Electron"): o verbo `plano` já existia
        para o plano inteiro; aqui ele carrega um ÚNICO passo — o mesmo que
        `PopUp._mostrar_cartao` desenha no cartão Qt — com os campos extras
        que faltavam no contrato original: `comando`, `precisa_autorizacao`,
        `texto_autorizacao` e `dupla_confirmacao`.
        """
        n = self.passo_i + 1
        total = len(self.plano)
        rotulo = f"Passo {n} de {total}: {passo.get('descricao', '')}"
        if d["motivos"]:
            rotulo += "\n(" + "; ".join(d["motivos"]) + ")"
        le_segredo = d.get("le_segredo", False)
        texto_autorizacao = (
            "Confirmo: pode ler esse arquivo de segredo" if le_segredo
            else "Tenho autorização (é meu, laboratório, ou por escrito)")
        pergunta = ("Tem certeza? Clique confirmar de novo para rodar"
                    if segunda_vez else "Confirma esse passo?")
        passo_ponte = {
            "rotulo": rotulo,
            "nivel": _nivel_ponte(d["nivel"]),
            "comando": passo.get("comando", ""),
            "precisa_autorizacao": bool(d["precisa_autorizacao"]),
            "texto_autorizacao": texto_autorizacao,
            "dupla_confirmacao": bool(d["dupla_confirmacao"]),
        }
        cartao_id = self._novo_cartao_id()
        self.ponte.enviar_plano([passo_ponte], _nivel_ponte(d["nivel"]), pergunta,
                                 cartao_id=cartao_id)

    def _reenviar_cartao_2conf(self):
        """Chamado depois do 1º clique do trilho de dupla confirmação
        (`confirmar_passo` já rodou e só armou `self._2conf`, o passo não
        avançou): o cartão volta com o mesmo passo, texto do 2º estágio."""
        d = getattr(self, "_risco_atual", None)
        if not d or self.passo_i >= len(self.plano):
            return
        self._enviar_cartao_do_passo(self.plano[self.passo_i], d, segunda_vez=True)

    def _reavaliar_confirmar(self):
        # No Qt isto habilita/desabilita o `b_confirmar` de verdade conforme
        # a caixa de autorização (widget real, nunca mostrado). Aqui não há
        # nada visível para reavaliar — a validação de "autorização marcada"
        # acontece do lado do Electron (HUD) antes de mandar a resposta, e de
        # novo do lado Python (a rede de segurança de verdade) em
        # `_confirmar_do_electron`, mais abaixo.
        pass

    # ---- o relógio de 500ms que já existe --------------------------------
    def atualizar(self):
        super().atualizar()
        aberto = self.escuta is not None
        if aberto != self._ultimo_microfone_enviado:
            self.ponte.enviar_microfone(aberto)
            self._ultimo_microfone_enviado = aberto
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


def _construir_ao_sair(app):
    """O que roda quando o Electron pede para sair ("Sair do DERVS") ou morre.
    Roda na thread de leitura da ponte — e `QApplication.quit()` chamado de
    fora da thread da tela não encerra nada: o Python ficava vivo, sem cara,
    com o microfone aberto, e o atalho seguinte "não fazia nada" (o 2º DERVS
    só avisava um Electron que já não existia). `invokeMethod` com conexão
    enfileirada leva o pedido até a thread certa.
    """
    def _ao_sair():
        QtCore.QMetaObject.invokeMethod(
            app, "quit", QtCore.Qt.ConnectionType.QueuedConnection)
    return _ao_sair


def _construir_ao_plano(motor: Motor):
    """`confirmar` faz o que o botão "Confirmar e rodar" do Qt já fazia
    (`motor.confirmar_passo`, que por sua vez chama `confirmar_plano_ok`
    sozinho quando o que está pendente é o plano inteiro, não um passo) —
    só que agora também precisa tratar `autorizado` (a caixa "Tenho
    autorização", que só existe como widget Qt escondido) e o trilho de
    dupla confirmação, que no Electron não tem um botão de verdade para
    trocar de texto sozinho.

    BUG DE CONCORRÊNCIA corrigido aqui: no Qt, esconder a barra do cartão
    era síncrono — widget escondido não recebe clique, então duplo-clique
    rápido nunca disparava duas respostas para o mesmo cartão. No Electron,
    "sumir o cartão anterior" é uma mensagem assíncrona que pode ainda não
    ter chegado quando o próximo clique sai — duas respostas em trânsito
    podiam rodar o passo errado, roubar uma das duas confirmações do
    trilho de dupla confirmação, ou rodar o mesmo passo destrutivo duas
    vezes (ver relato desta etapa, com reprodução dos três casos). A
    correção: cada cartão enviado carrega um `cartao_id` novo
    (`Motor._novo_cartao_id`); qualquer resposta cujo `cartao_id` não bata
    exatamente com `motor._cartao_pendente` é uma mensagem desatualizada e
    é ignorada em silêncio — não é erro, só não executa nada. Zerar
    `_cartao_pendente` ANTES de decidir o que fazer com a resposta válida
    também descarta uma segunda resposta duplicada da MESMA mensagem
    original.
    """
    def _ao_plano(resposta, autorizado=False, cartao_id=None):
        if motor._cartao_pendente is None or cartao_id != motor._cartao_pendente:
            return   # resposta desatualizada — nenhum cartão espera por ela
        motor._cartao_pendente = None
        if resposta == "confirmar":
            _confirmar_do_electron(motor, bool(autorizado))
        elif resposta == "cancelar":
            motor.cancelar_plano()
    return _ao_plano


def _confirmar_do_electron(motor: Motor, autorizado: bool):
    """A mesma decisão que `confirmar_passo()` (`dervs.py:1392`) toma com
    `self.b_auth.isChecked()` — só que a caixa marcada agora vem da resposta
    do Electron, não de um clique num widget visível.

    `em_passo` é verdadeiro exatamente quando `confirmar_passo()` cairia no
    ramo de PASSO (não no de plano inteiro): `_aguardando_ok` já é falso (o
    plano inteiro já foi aprovado) e existe um `_risco_atual` pendente (um
    passo destrutivo mostrou o cartão e está esperando o dono).
    """
    d = getattr(motor, "_risco_atual", None)
    em_passo = (not motor._aguardando_ok) and d is not None
    if not em_passo:
        # aprovação do plano inteiro — `confirmar_passo()` chama
        # `confirmar_plano_ok()` sozinho; `Motor.confirmar_plano_ok` já
        # cuida de limpar o cartão da ponte.
        motor.confirmar_passo()
        return
    if d.get("precisa_autorizacao") and not autorizado:
        # o Electron não deveria ter deixado mandar sem a caixa marcada —
        # esta checagem aqui é a rede de segurança de verdade, a mesma que
        # o Qt faz com `b_auth.isChecked()` antes de rodar qualquer coisa.
        return
    if autorizado:
        # simula a caixa marcada no widget Qt real (ainda existe, só está
        # escondido) — `confirmar_passo()` original lê `b_auth.isChecked()`
        # direto (`dervs.py:1409`), então isto reusa a validação original
        # sem duplicar a lógica dela aqui.
        motor.b_auth.setChecked(True)
    ja_esperava_2conf = motor._2conf
    motor.confirmar_passo()
    if not ja_esperava_2conf and motor._2conf:
        # 1º clique do trilho de dupla confirmação: `confirmar_passo()` só
        # armou `self._2conf` e voltou — o passo não rodou. Reenvia o cartão
        # com o texto do 2º estágio.
        motor._reenviar_cartao_2conf()
    else:
        # o passo rodou de verdade (ou era o 2º clique) — tira o cartão da
        # tela, o mesmo que o Qt faz com `self.barra.hide()` logo antes de
        # `self._rodar_comando(...)`.
        motor.ponte.enviar_plano([], "reversivel", "")


def _encerrar(motor: Motor, ponte: PonteElectron, posse, parar_sistema: threading.Event):
    """O que o fechamento do app faz: desliga tudo o que a `PopUp` deixou de
    pé (`dervs.encerrar_tudo`, a mesma função de sempre — nada reescrito),
    para a thread do painel de sistema, fecha o processo do Electron, e libera
    a trava de instância única."""
    parar_sistema.set()
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

    _ao_sair = _construir_ao_sair(app)   # o aboutToQuit chama `_encerrar`

    # `ao_plano` precisa do `motor`, e o `motor` precisa da `ponte` — a mesma
    # indireção de `ponte_alvo` acima resolve a dependência circular sem
    # mexer em atributo privado da `PonteElectron`.
    ao_plano_alvo = []

    def _ao_plano_inicial(resposta, autorizado=False, cartao_id=None):
        if ao_plano_alvo:
            ao_plano_alvo[0](resposta, autorizado, cartao_id)

    ao_microfone_alvo = []

    def _ao_microfone_inicial(ligar):
        if ao_microfone_alvo:
            ao_microfone_alvo[0](ligar)

    ponte = PonteElectron(ao_sair=_ao_sair, ao_plano=_ao_plano_inicial,
                          ao_pronto=lambda: None, ao_microfone=_ao_microfone_inicial)
    motor = Motor(ponte)
    ao_microfone_alvo.append(motor.pedir_microfone)
    ao_plano_alvo.append(_construir_ao_plano(motor))
    ponte_alvo.append(_construir_me_chamaram(ponte))

    conf = config.carregar()
    try:
        ponte.abrir(CAMINHO_ELECTRON, env_extra={"DERVS_APP_URL": conf["dervs_app_url"]})
    except FileNotFoundError as e:
        sys.stderr.write("dervs: %s\n" % e)
        sys.stderr.flush()
        dervs.encerrar_tudo(motor)
        posse.soltar()
        sys.exit(1)

    # Painel de sistema (CPU/RAM/disco reais, fase 1 da esteira
    # dervs-painel-completo): thread própria, à parte da `Escuta`/`Voz`, que
    # nunca deveria esperar por elas nem ser bloqueada por elas.
    parar_sistema = threading.Event()
    sistema.iniciar_loop_sistema(ponte, parar_sistema)

    app.aboutToQuit.connect(lambda: _encerrar(motor, ponte, posse, parar_sistema))
    app.exec()


if __name__ == "__main__":
    main()
