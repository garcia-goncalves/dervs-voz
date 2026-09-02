#!/usr/bin/env python3
"""Testes da lógica pura do navegador autônomo.

O laço de verdade (rodar_tarefa) precisa de Chrome e internet — esse a gente
testa na máquina, à mão. Aqui cobrimos o que é função pura: montar o estado da
página para o modelo, normalizar a ação que ele devolve, reconhecer o erro de
'Chrome já aberto', e o executor de UMA ação com uma página falsa (sem abrir
navegador nenhum)."""
import dervs_browser as nav


# --- montar_estado: vira texto compacto que o modelo lê -----------------------
def test_montar_estado_lista_elementos_com_numero():
    els = [{"ref": 0, "tag": "a", "tipo": "link", "nome": "Entrar"},
           {"ref": 1, "tag": "input", "tipo": "search", "nome": "Pesquisar"}]
    txt = nav.montar_estado("https://x.com", "Início", els, "achar algo", [])
    assert "OBJETIVO: achar algo" in txt
    assert "0: a" in txt and "Entrar" in txt
    assert "1: input" in txt and "Pesquisar" in txt
    assert "URL ATUAL: https://x.com" in txt


def test_montar_estado_sem_elementos_avisa():
    txt = nav.montar_estado("about:blank", "", [], "obj", [])
    assert "nenhum elemento interativo" in txt


def test_montar_estado_mostra_historico_recente():
    hist = [f"passo {i}: fiz coisa {i}" for i in range(10)]
    txt = nav.montar_estado("u", "t", [], "obj", hist)
    # só as últimas 6 aparecem
    assert "coisa 9" in txt
    assert "coisa 3" not in txt


# --- normalizar_acao: ação desconhecida vira 'desistir' -----------------------
def test_normalizar_acao_valida_preserva():
    a = nav.normalizar_acao({"acao": "clicar", "ref": 2})
    assert a["acao"] == "clicar" and a["ref"] == 2


def test_normalizar_acao_desconhecida_vira_desistir():
    a = nav.normalizar_acao({"acao": "explodir"})
    assert a["acao"] == "desistir"
    assert a["motivo"]


def test_normalizar_acao_maiuscula_normaliza():
    a = nav.normalizar_acao({"acao": "  PRONTO  ", "resultado": "ok"})
    assert a["acao"] == "pronto"


# --- _extrair_json: puxa o objeto de dentro de texto/cerca --------------------
def test_extrair_json_com_texto_em_volta():
    d = nav._extrair_json('lixo antes {"acao":"esperar"} lixo depois')
    assert d["acao"] == "esperar"


def test_extrair_json_vazio_levanta():
    import pytest
    with pytest.raises(ValueError):
        nav._extrair_json("")


# --- _resumo_erro_perfil: reconhece 'Chrome já aberto' ------------------------
def test_resumo_erro_perfil_reconhece_lock():
    msg = "Failed to launch: SingletonLock exists, profile in use"
    r = nav._resumo_erro_perfil(msg)
    assert r and "Chrome" in r and "Feche" in r


def test_resumo_erro_perfil_ignora_outro_erro():
    assert nav._resumo_erro_perfil("timeout ao carregar a página") is None


# --- _executar_acao: com uma página FALSA (nada abre de verdade) --------------
class _PaginaFalsa:
    def __init__(self, quebrar=None):
        self.chamadas = []
        self._quebrar = quebrar  # nome de método que deve levantar exceção
        self.mouse = self

    def _reg(self, nome, *a, **k):
        self.chamadas.append((nome, a, k))
        if self._quebrar == nome:
            raise RuntimeError("boom")

    def goto(self, *a, **k): self._reg("goto", *a, **k)
    def click(self, *a, **k): self._reg("click", *a, **k)
    def fill(self, *a, **k): self._reg("fill", *a, **k)
    def press(self, *a, **k): self._reg("press", *a, **k)
    def wheel(self, *a, **k): self._reg("wheel", *a, **k)


def test_executar_navegar_completa_url():
    p = _PaginaFalsa()
    r = nav._executar_acao(p, {"acao": "navegar", "url": "example.com"}, [])
    assert "naveguei" in r
    # completou o esquema https://
    assert p.chamadas[0][1][0].startswith("https://example.com")


def test_executar_clicar_usa_seletor_do_ref():
    p = _PaginaFalsa()
    els = [{"ref": 5, "nome": "Botão X"}]
    r = nav._executar_acao(p, {"acao": "clicar", "ref": 5}, els)
    assert "cliquei" in r and "Botão X" in r
    assert p.chamadas[0][1][0] == '[data-grim-ref="5"]'


def test_executar_digitar_recusa_campo_senha():
    p = _PaginaFalsa()
    els = [{"ref": 3, "nome": "senha", "senha": True}]
    r = nav._executar_acao(p, {"acao": "digitar", "ref": 3, "texto": "segredo"}, els)
    assert "recusei" in r
    # e NÃO chamou fill (não digitou nada)
    assert p.chamadas == []


def test_executar_digitar_com_enter():
    p = _PaginaFalsa()
    els = [{"ref": 1, "nome": "busca", "senha": False}]
    r = nav._executar_acao(p, {"acao": "digitar", "ref": 1, "texto": "oi", "enter": True}, els)
    assert "digitei" in r and "Enter" in r
    nomes = [c[0] for c in p.chamadas]
    assert "fill" in nomes and "press" in nomes


def test_executar_acao_que_falha_vira_texto():
    p = _PaginaFalsa(quebrar="click")
    els = [{"ref": 0, "nome": "x"}]
    r = nav._executar_acao(p, {"acao": "clicar", "ref": 0}, els)
    assert "falhou" in r  # erro virou texto, não exceção


def test_executar_clicar_sem_ref_avisa():
    p = _PaginaFalsa()
    r = nav._executar_acao(p, {"acao": "clicar"}, [])
    assert "sem número" in r


# --- rodar_para_app: lê o JSON marcado que a venv imprime ---------------------
class _ProcFalso:
    def __init__(self, stdout="", stderr=""):
        self.stdout, self.stderr = stdout, stderr


# A partir de 02/09/2026 o navegador não usa mais `subprocess.run`, e sim
# `dervs_processos.rodar_com_arvore`. Não foi troca de gosto: o `run` mata só o
# Python que comandava o navegador e deixa vivo o `chrome.exe` que ele abriu,
# segurando o perfil de verdade do dono. O dublê tem de ficar na costura nova,
# senão estes testes passariam sem exercitar o código que roda.
def test_rodar_para_app_le_json_marcado(monkeypatch):
    saida = ("Chrome barulho no stdout\n"
             + nav._MARCADOR + '{"codigo":0,"saida":"pronto: achei 3 não lidos","tipo":"navegador"}\n')
    import dervs_processos
    monkeypatch.setattr(dervs_processos, "rodar_com_arvore",
                        lambda *a, **k: _ProcFalso(stdout=saida))
    # garante que o caminho da venv "existe" para não cair no fallback in-process
    monkeypatch.setattr(nav.os.path, "exists", lambda p: True)
    r = nav.rodar_para_app("contar não lidos")
    assert r["codigo"] == 0 and "não lidos" in r["saida"]


def test_rodar_para_app_sem_marcador_vira_erro(monkeypatch):
    import dervs_processos
    monkeypatch.setattr(dervs_processos, "rodar_com_arvore",
                        lambda *a, **k: _ProcFalso(stdout="nada útil", stderr="deu ruim"))
    monkeypatch.setattr(nav.os.path, "exists", lambda p: True)
    r = nav.rodar_para_app("x")
    assert r["codigo"] == 1 and "não devolveu resultado" in r["saida"]


def test_rodar_para_app_objetivo_vazio():
    assert nav.rodar_para_app("")["codigo"] == 1
