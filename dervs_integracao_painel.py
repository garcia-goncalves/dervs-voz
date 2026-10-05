#!/usr/bin/env python3
"""DERVS — a tela "Integração" do painel: a cola entre a tela LOCAL (Electron) e as
peças que ligam o DERVS-VOZ ao resto (cérebros, painel web, terminal SSH).

Quatro blocos, todos só do dono, todos por CLIQUE:
  1. Cérebro   — mostra `Seletor.estado()` e deixa escolher entre claude_code e hermes.
  2. Painel web — estado da ponte, a FILA de pedidos vindos de lá (só "Dispensar": não
                  existe "executar" aqui) e os AVISOS, com "Pedir conserto" quando o
                  aviso traz `[alerta:<id>] `.
  3. Terminal SSH — leitura roda direto; o que muda servidor mostra o CARTÃO e só anda
                  depois de UMA segunda confirmação explícita de clique.

Por que este módulo existe separado da UI e de `dervs_electron.py`: toda a lógica que
decide algo (o que vira botão, o que o clique pode fazer, o que é recusado) fica
aqui, onde dá para testar sem Electron. A tela só desenha e só PEDE.

Isolamento (não negociável): este é o ÚNICO módulo do repositório que importa o
terminal SSH (teste de isolamento em `test_dervs_ssh.py`). O Claude, a ponte do Claude,
o cérebro e a ponte web NUNCA passam por aqui: nada do que a tela mostra ou faz chega
a eles, e o CARTÃO do clique (a senha de uso) fica em memória neste objeto — a tela
nunca o vê, só manda "confirmo a proposta X".
"""
import datetime
import json
import os
import re
import secrets
import threading
import time

import dervs_config
import dervs_log_acoes

TETO_AVISOS = 100              # o arquivo de avisos nunca passa disso (o mais antigo sai)
TETO_TEXTO_AVISO = 500         # o texto do painel web já vem cortado em 500; aqui de novo
TETO_FILA_NA_TELA = 50
MAX_CARTOES = 10               # propostas SSH esperando o clique da segunda confirmação
VALIDADE_CARTAO_S = 15 * 60    # a mesma validade do Motor de aprovação
TETO_SAIDA_NA_TELA = 16000     # caracteres; a saída inteira (até 64 KiB) não cabe na linha da ponte

# Só este formato vira botão "Pedir conserto": o id vai para o painel web como está.
_ALERTA = re.compile(r"\[alerta:([A-Za-z0-9._:-]{1,200})\] (.*)", re.DOTALL)

CEREBROS_ROTULO = {"claude_code": "Claude Code", "hermes": "Hermes Agent", "jev": "JEV"}
CEREBROS_ESCOLHIVEIS = ("claude_code", "hermes")


def arquivo_avisos_padrao() -> str:
    return os.path.join(dervs_config.CONFIG_DIR, "avisos_web.jsonl")


def extrair_alerta(texto) -> tuple:
    """`[alerta:<id>] frase` -> (id, frase). Sem o prefixo exato, (None, texto)."""
    m = _ALERTA.fullmatch(texto) if isinstance(texto, str) else None
    if m is None:
        return None, texto if isinstance(texto, str) else ""
    return m.group(1), m.group(2).strip()


def frase_do_conserto(r: dict) -> str:
    """O retorno de `PonteWeb.pedir_conserto` em frase para leigo."""
    if not r.get("ok"):
        return str(r.get("motivo") or "Não consegui pedir o conserto agora.")[:300]
    if r.get("novo"):
        frase = ("Pedi ao painel web que prepare o conserto. Ele só anda quando você der o "
                 "\"Pode fazer\" lá no painel.")
    else:
        frase = "O painel já tinha esse pedido de conserto. É só dar o \"Pode fazer\" lá."
    if r.get("aviso"):
        frase += " " + str(r["aviso"])[:300]
    return frase


def frase_da_ponte(ponte, motivo_inicial: str = "") -> dict:
    """Estado da ponte com o painel web em linguagem leiga: {"codigo", "frase"}.
    `codigo`: ligada | calma | com_problema | desligada (a tela só usa para a cor)."""
    if ponte is None or not getattr(ponte, "ligada", False):
        motivo = str(motivo_inicial or "").strip()
        return {"codigo": "desligada", "frase": "Desligada. " + (
            motivo[:300] if motivo else "O DERVS-VOZ não está conversando com o painel web.")}
    motivo = getattr(ponte, "motivo", None)
    if not motivo:
        return {"codigo": "ligada", "frase": "Ligada: o DERVS-VOZ e o painel web estão conversando."}
    if getattr(ponte, "calma", False):
        return {"codigo": "calma",
                "frase": "Em modo calmo: o painel web ainda não publicou a ponte, então olho de "
                         "novo só a cada 5 minutos, sem alarme. " + str(motivo)[:300]}
    return {"codigo": "com_problema",
            "frase": "Ligada, mas não consegui falar com o painel agora. " + str(motivo)[:300]}


def frases_dos_cerebros(estado: dict) -> dict:
    """`Seletor.estado()` pronto para a tela: cada cérebro com rótulo, se dá para
    escolher, e uma frase. O JEV é "triagem rápida — não conversa" e nunca é escolhível."""
    ativo = estado.get("cerebro_ativo")
    saida = []
    for nome, info in (estado.get("cerebros") or {}).items():
        disponivel = bool(info.get("disponivel"))
        motivo = str(info.get("motivo") or "").strip()
        escolhivel = nome in CEREBROS_ESCOLHIVEIS
        if nome == "jev":
            frase = "Triagem rápida — não conversa. "
            frase += ("Está disponível." if disponivel else
                      "Indisponível: " + (motivo or "sem motivo informado") + ".")
        elif disponivel:
            frase = "Disponível."
        else:
            frase = "Indisponível: " + (motivo or "sem motivo informado") + "."
        saida.append({"nome": nome, "rotulo": CEREBROS_ROTULO.get(nome, nome[:40]),
                      "disponivel": disponivel, "escolhivel": escolhivel,
                      "ativo": nome == ativo and escolhivel, "frase": frase[:400]})
    return {"ativo": ativo, "cerebros": saida}


def texto_do_cartao(apelido: str, comando: str) -> dict:
    """O que o dono lê antes do segundo clique. As duas frases repetem as do item
    `executar_ssh` do Motor de aprovação (há teste que confere que não se afastam)."""
    return {
        "servidor": apelido, "comando": comando, "risco": "alto",
        "o_que_muda": f"Vai rodar o comando {comando} no servidor {apelido}; o servidor pode mudar.",
        "como_desfazer": "O DERVS não desfaz isto; o registro guarda exatamente o que rodou.",
    }


class IntegracaoLocal:
    def __init__(self, ponte, *, motor_fabrica, seletor_fn, ponte_web_fn, tratador=None,
                 terminal_fabrica=None, arquivo_avisos=None, arquivo_hosts=None,
                 agora=datetime.datetime.now, monotonico=time.monotonic):
        """`ponte` é a PonteElectron (só usa `enviar_integracao`). `motor_fabrica()` é o
        Motor de aprovação JÁ existente (nunca um segundo). `seletor_fn()` devolve o
        Seletor compartilhado com a ponte web. `ponte_web_fn()` devolve `(PonteWeb|None,
        motivo_inicial)`. `terminal_fabrica(motor)` só existe para teste: sem ela o
        terminal nasce na primeira vez que o dono usa o SSH."""
        self._ponte = ponte
        self._motor_fabrica = motor_fabrica
        self._seletor_fn = seletor_fn
        self._ponte_web_fn = ponte_web_fn
        self.tratador = tratador
        self._terminal_fabrica = terminal_fabrica
        self._arquivo_avisos = arquivo_avisos or arquivo_avisos_padrao()
        self._arquivo_hosts = arquivo_hosts
        self._agora = agora
        self._mono = monotonico
        self._terminal_obj = None
        self._trava = threading.Lock()           # terminal, cartões
        self._trava_avisos = threading.Lock()
        self._cartoes = {}                       # proposta_id -> {"proposta", "cartao", "criado"}
        self._conserto_em_curso = set()

    # ------------------------------------------------------------ entrada da tela
    def tratar(self, verbo: str, dados: dict):
        """Ponto único dos verbos `integracao_*` (já validados pela ponte). Tudo roda
        em thread: Hermes consulta o WSL, o SSH leva até 60 s, e a thread leitora da
        ponte não pode parar. Devolve a thread (os testes a esperam)."""
        t = threading.Thread(target=self._seguro, args=(verbo, dados or {}), daemon=True)
        t.start()
        return t

    def _seguro(self, verbo, dados):
        try:
            self._despachar(verbo, dados)
        except Exception as erro:   # a tela nunca fica esperando em silêncio
            self._enviar("mensagem", {"ok": False, "texto": "Algo falhou por dentro "
                                      f"({type(erro).__name__}). Nada foi feito."})

    def _despachar(self, verbo, dados):
        if verbo == "integracao_pedir":
            self.enviar_tudo()
        elif verbo == "integracao_cerebro":
            self._escolher_cerebro(dados.get("nome"))
        elif verbo == "integracao_dispensar":
            self._dispensar(dados.get("id"))
        elif verbo == "integracao_conserto":
            self._pedir_conserto(dados.get("aviso_id"))
        elif verbo == "integracao_ssh_rodar":
            self._ssh_rodar(dados.get("apelido"), dados.get("comando"))
        elif verbo == "integracao_ssh_confirmar":
            self._ssh_confirmar(dados.get("proposta_id"), dados.get("segunda"))
        elif verbo == "integracao_ssh_cancelar":
            self._ssh_cancelar(dados.get("proposta_id"))

    def _enviar(self, parte, dados):
        try:
            self._ponte.enviar_integracao(parte, dados)
        except Exception:
            pass    # sem tela não há a quem contar; a voz segue

    def enviar_tudo(self):
        self.enviar_cerebros()
        self.enviar_web()
        self.enviar_fila()
        self.enviar_avisos()
        self.enviar_ssh_estado()

    # ------------------------------------------------------------ 1. cérebro
    def enviar_cerebros(self):
        self._enviar("cerebros", frases_dos_cerebros(self._seletor_fn().estado()))

    def _escolher_cerebro(self, nome):
        if nome not in CEREBROS_ESCOLHIVEIS:
            ok, motivo = False, ("O JEV faz só triagem rápida; ele não pode ser o cérebro que conversa."
                                 if nome == "jev" else "Não conheço esse cérebro.")
        else:
            ok, motivo = self._seletor_fn().escolher(nome)
        self._enviar("mensagem", {"ok": bool(ok), "texto": (
            f"Pronto: agora o cérebro ativo é o {CEREBROS_ROTULO[nome]}." if ok else motivo)})
        self.enviar_cerebros()

    # ------------------------------------------------------------ 2a. estado da ponte e fila
    def enviar_web(self):
        ponte, motivo = self._ponte_web_fn()
        self._enviar("web", frase_da_ponte(ponte, motivo))

    def fila(self) -> list:
        if self.tratador is None:
            return []
        itens = []
        for i in self.tratador.pendentes()[:TETO_FILA_NA_TELA]:
            itens.append({"id": str(i.get("id") or "")[:64], "quando": str(i.get("quando") or "")[:30],
                          "tipo": str(i.get("tipo") or "")[:30], "alvo": str(i.get("alvo") or "")[:80],
                          "texto": str(i.get("texto") or "")[:TETO_TEXTO_AVISO]})
        return itens

    def enviar_fila(self):
        self._enviar("fila", {"itens": self.fila()})

    def _dispensar(self, pedido_id):
        ok = bool(self.tratador is not None and self.tratador.dispensar(pedido_id))
        self._enviar("mensagem", {"ok": ok, "texto": (
            "Pedido dispensado. Nada foi executado." if ok else "Esse pedido não está mais na fila.")})
        self.enviar_fila()

    # ------------------------------------------------------------ 2b. avisos
    def ao_aviso(self, texto, alvo=""):
        """Chamado pelo tratador da ponte web. NUNCA levanta (quem chama é a thread da
        ponte). O texto é dado de terceiro: entra redigido e cortado."""
        try:
            self.registrar_aviso(texto, alvo)
        except Exception:
            pass

    def registrar_aviso(self, texto, alvo=""):
        bruto = dervs_log_acoes.redigir({
            "texto": str(texto or "")[:TETO_TEXTO_AVISO], "alvo": str(alvo or "")[:80]})
        alerta_id, _frase = extrair_alerta(bruto["texto"])
        registro = {"id": secrets.token_hex(6),
                    "quando": self._agora().isoformat(timespec="seconds"),
                    "alvo": bruto["alvo"], "texto": bruto["texto"],
                    "alerta_id": alerta_id, "conserto": ""}
        with self._trava_avisos:
            lista = self._ler_avisos()
            lista.append(registro)
            self._gravar_avisos(lista[-TETO_AVISOS:])
        self.enviar_avisos()
        return registro

    def _ler_avisos(self) -> list:
        saida = []
        try:
            with open(self._arquivo_avisos, "r", encoding="utf-8") as f:
                for linha in f:
                    try:
                        item = json.loads(linha)
                    except ValueError:
                        continue
                    if isinstance(item, dict) and isinstance(item.get("id"), str):
                        saida.append(item)
        except OSError:
            pass
        return saida

    def _gravar_avisos(self, lista):
        os.makedirs(os.path.dirname(self._arquivo_avisos) or ".", exist_ok=True)
        temporario = self._arquivo_avisos + ".tmp"
        with open(temporario, "w", encoding="utf-8", newline="\n") as f:
            for item in lista:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        os.replace(temporario, self._arquivo_avisos)

    def avisos(self) -> list:
        """Os avisos para a tela (mais novo primeiro). `pode_conserto` só é True se o
        prefixo `[alerta:<id>] ` bateu na regex estrita; sem ele, sem botão."""
        with self._trava_avisos:
            lista = self._ler_avisos()
        saida = []
        for a in reversed(lista[-TETO_AVISOS:]):
            saida.append({"id": a["id"][:32], "quando": str(a.get("quando") or "")[:30],
                          "alvo": str(a.get("alvo") or "")[:80],
                          "texto": str(a.get("texto") or "")[:TETO_TEXTO_AVISO],
                          "pode_conserto": bool(a.get("alerta_id")),
                          "conserto": str(a.get("conserto") or "")[:400]})
        return saida

    def enviar_avisos(self):
        self._enviar("avisos", {"itens": self.avisos()})

    def _pedir_conserto(self, aviso_id):
        """SÓ por clique do dono (o verbo nasce no botão). O id do alerta não vem da
        tela: vem do aviso gravado aqui, então a tela não consegue pedir conserto de
        um alerta que o painel web nunca avisou."""
        with self._trava_avisos:
            alvo = next((a for a in self._ler_avisos() if a["id"] == aviso_id), None)
            achou = alvo is not None and bool(alvo.get("alerta_id"))
            if achou:
                if aviso_id in self._conserto_em_curso:
                    return
                self._conserto_em_curso.add(aviso_id)
        if not achou:
            self._enviar("mensagem", {"ok": False, "texto": "Este aviso não tem um alerta para consertar."})
            return
        try:
            ponte, motivo = self._ponte_web_fn()
            if ponte is None:
                r = {"ok": False, "motivo": "A ponte com o painel web está desligada. " + str(motivo or "")}
            else:
                _id, frase = extrair_alerta(alvo["texto"])
                r = ponte.pedir_conserto(alvo["alerta_id"], frase)
            texto = frase_do_conserto(r)
            with self._trava_avisos:
                lista = self._ler_avisos()
                for a in lista:
                    if a["id"] == aviso_id:
                        a["conserto"] = texto
                self._gravar_avisos(lista)
            self._enviar("mensagem", {"ok": bool(r.get("ok")), "texto": texto})
        finally:
            self._conserto_em_curso.discard(aviso_id)
        self.enviar_avisos()

    # ------------------------------------------------------------ 3. terminal SSH
    def _terminal(self):
        with self._trava:
            if self._terminal_obj is None:
                motor = self._motor_fabrica()
                if self._terminal_fabrica is not None:
                    self._terminal_obj = self._terminal_fabrica(motor)
                else:
                    import dervs_putty
                    import dervs_ssh
                    # o LogAcoes do Motor, nunca um segundo: duas instâncias sobre o mesmo
                    # arquivo quebrariam a corrente de hashes
                    self._terminal_obj = dervs_ssh.TerminalSSH(
                        motor.log, dervs_ssh.AprovadorMotor(motor), arquivo_hosts=self._arquivo_hosts,
                        leitor_putty=dervs_putty.ler_sessoes_do_registro)
            return self._terminal_obj

    def arquivo_de_hosts(self) -> str:
        if self._arquivo_hosts:
            return self._arquivo_hosts
        import dervs_ssh
        return dervs_ssh.arquivo_hosts_padrao()

    def enviar_ssh_estado(self):
        try:
            apelidos = self._terminal().apelidos()
        except Exception:
            apelidos = []
        self._enviar("ssh", {"apelidos": apelidos[:50], "arquivo_hosts": self.arquivo_de_hosts()})

    def _podar_cartoes(self, agora):
        for pid in [p for p, v in self._cartoes.items() if agora - v["criado"] > VALIDADE_CARTAO_S]:
            del self._cartoes[pid]
        while len(self._cartoes) >= MAX_CARTOES:
            del self._cartoes[min(self._cartoes, key=lambda p: self._cartoes[p]["criado"])]

    def _resultado_ssh(self, r: dict, apelido, comando, tipo):
        saida = str(r.get("saida") or "")
        self._enviar("ssh_resultado", {
            "ok": bool(r.get("ok")), "tipo": tipo, "apelido": str(apelido)[:40],
            "comando": str(comando)[:400], "rc": r.get("rc") if isinstance(r.get("rc"), int) else None,
            "saida": saida[:TETO_SAIDA_NA_TELA], "truncada": bool(r.get("truncada")) or len(saida) > TETO_SAIDA_NA_TELA,
            "motivo": str(r.get("motivo") or "")[:400]})

    def _ssh_rodar(self, apelido, comando):
        r = self._terminal().rodar(apelido, comando)
        if r.get("precisa_clique"):
            self._montar_cartao(r["proposta"])
        else:
            self._resultado_ssh(r, apelido, comando, "leitura")

    def apelidos(self) -> list:
        """Servidores que a voz pode citar (arquivo do dono + sessões do PuTTY). Nunca levanta."""
        try:
            return self._terminal().apelidos()
        except Exception:
            return []

    def ssh_por_voz(self, apelido, comando, pergunta=None) -> str:
        """O mesmo caminho do clique da tela, para o pedido falado: leitura roda e volta resumida
        em voz; o que muda servidor só vira o CARTÃO na tela (a aprovação é sempre o clique).
        Devolve a frase que o DERVS fala. Bloqueia até 60 s: chamar de uma thread."""
        if pergunta is not None:     # "pergunta pro Claude da VPS": nunca é leitura, sempre cartão
            import dervs_ssh
            comando = dervs_ssh.comando_claude_da_vps(pergunta)
            if comando is None:
                return "Não consegui transformar essa pergunta num comando seguro. Nada foi feito."
        r = self._terminal().rodar(apelido, comando)
        if r.get("precisa_clique"):
            self._montar_cartao(r["proposta"])
            return (f"Isso mexe no servidor {apelido}. Pus o cartão na tela Integração, "
                    "com o comando exato. Só roda se você confirmar lá.")
        self._resultado_ssh(r, apelido, comando, "leitura")
        if not r.get("ok"):
            return f"Não rodei no {apelido}: {str(r.get('motivo') or 'recusado')[:160]}"
        linhas = [l.strip() for l in str(r.get("saida") or "").splitlines() if l.strip()]
        resumo = " / ".join(linhas[:4])[:240]
        return (f"No {apelido}: {resumo}. A saída inteira está na tela Integração."
                if resumo else f"No {apelido}: rodou sem saída.")

    def _montar_cartao(self, proposta: dict):
        ref = proposta.get("aprovacao") or {}
        motor = self._motor_fabrica()
        status = motor.status(ref.get("relatorio_id"))
        item = next((i for i in (status or {}).get("itens", []) if i["id"] == ref.get("item_id")), None)
        if (item is None or item["acao"] != "executar_ssh" or item["risco"] != "alto"
                or item["alvo"] != f"ssh:{proposta['apelido']}"):
            self._resultado_ssh({"ok": False, "motivo": "A aprovação não reconheceu esse comando. "
                                                        "Nada foi feito."},
                                proposta.get("apelido", ""), proposta.get("comando", ""), "muda_estado")
            return
        cartao = motor.abrir_cartao(ref["relatorio_id"])
        if cartao is None:
            self._resultado_ssh({"ok": False, "motivo": "A proposta venceu antes de abrir o cartão. "
                                                        "Envie o comando de novo."},
                                proposta["apelido"], proposta["comando"], "muda_estado")
            return
        with self._trava:
            self._podar_cartoes(self._mono())
            self._cartoes[proposta["proposta_id"]] = {"proposta": proposta, "cartao": cartao,
                                                      "criado": self._mono()}
        self._enviar("ssh_cartao", dict(
            texto_do_cartao(proposta["apelido"], proposta["comando"]),
            proposta_id=proposta["proposta_id"],
            valida_min=int(VALIDADE_CARTAO_S // 60)))

    def _ssh_cancelar(self, proposta_id):
        with self._trava:
            tinha = self._cartoes.pop(proposta_id, None) is not None
        self._enviar("ssh_cancelado", {"proposta_id": str(proposta_id)[:40], "tinha": tinha})

    def _ssh_confirmar(self, proposta_id, segunda):
        """A SEGUNDA confirmação. Só vale com `segunda` exatamente True, com um cartão
        guardado aqui e dentro do prazo; o cartão sai do dicionário ANTES de aprovar,
        então um duplo clique não aprova duas vezes."""
        def falha(texto, apelido="", comando=""):
            self._resultado_ssh({"ok": False, "motivo": texto}, apelido, comando, "muda_estado")
        if segunda is not True:
            return falha("Falta a segunda confirmação. Nada foi feito.")
        with self._trava:
            guardado = self._cartoes.pop(proposta_id, None) if isinstance(proposta_id, str) else None
        if guardado is None or self._mono() - guardado["criado"] > VALIDADE_CARTAO_S:
            return falha("Esta proposta não está mais esperando (passou o prazo ou já foi usada). "
                         "Envie o comando de novo.")
        proposta, ref = guardado["proposta"], guardado["proposta"]["aprovacao"]
        apelido, comando = proposta["apelido"], proposta["comando"]
        motor = self._motor_fabrica()
        aprovado = motor.aprovar(ref["relatorio_id"], [ref["item_id"]], origem="clique",
                                 cartao=guardado["cartao"], dupla_confirmacao=[ref["item_id"]])
        if not aprovado.get("ok"):
            return falha(str(aprovado.get("motivo") or "A aprovação recusou.") + " Nada foi feito.",
                         apelido, comando)
        registro = aprovado["registro"]
        prova = {"registro_id": registro["id"], "token": registro["token"],
                 "relatorio_id": ref["relatorio_id"]}
        r = self._terminal().executar(proposta["proposta_id"], prova)
        self._resultado_ssh(r, apelido, comando, "muda_estado")
