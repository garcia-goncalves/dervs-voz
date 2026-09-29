#!/usr/bin/env python3
"""Testes da Central do PC (onda D): coletores com saída gravada, nota,
tendência, resumo, orquestração e proposta de limpeza. Nada aqui toca o
Windows de verdade — `rodar` é sempre um dublê.

Rodar: python -m pytest test_dervs_central.py -q
"""
import datetime
import json
import os
import time
import types

import pytest

from dervs_central import (atualizacoes, base, central, disco, drivers, energia, eventos,
                           explicacoes, inicializacao, limpeza, nota, processos, repositorios,
                           resumo, seguranca, temporarios, tendencia, winget)

AGORA = datetime.datetime(2026, 9, 29, 12, 0, 0)


def falso(respostas: dict):
    """Dublê de `rodar`: devolve a resposta cuja chave aparece na consulta."""
    def rodar(consulta, timeout=None):
        for chave, saida in respostas.items():
            if chave in consulta:
                if isinstance(saida, Exception):
                    raise saida
                return saida if isinstance(saida, str) else json.dumps(saida)
        return ""
    return rodar


# ------------------------------------------------------------------ base
def test_como_lista_aceita_objeto_solto_vazio_e_lista():
    assert base.como_lista("") == []
    assert base.como_lista('{"a":1}') == [{"a": 1}]
    assert base.como_lista('[{"a":1},{"a":2}]') == [{"a": 1}, {"a": 2}]


def test_consulta_com_json_ruim_vira_erro_de_consulta():
    with pytest.raises(base.ErroConsulta):
        base.consultar(lambda c, t=None: "isto não é json", "x")


def test_aspas_dobra_aspa_simples():
    assert base.aspas("C:\\o'brien\\a.exe") == "'C:\\o''brien\\a.exe'"


def test_negado_reconhece_acesso_negado_em_ingles_e_portugues():
    assert base._negado("Access is denied")
    assert base._negado("Acesso negado.")
    assert not base._negado("tudo certo")


# ------------------------------------------------------------------ disco
class Particao:
    def __init__(self, ponto, opts=""):
        self.mountpoint, self.opts = ponto, opts


def psutil_falso(uso):
    def disk_usage(p):
        if p not in uso:
            raise OSError("sem mídia")
        return types.SimpleNamespace(total=uso[p][0], free=uso[p][1])
    return types.SimpleNamespace(
        disk_partitions=lambda all=False: [Particao(p, "cdrom" if p == "D:\\" else "rw") for p in uso],
        disk_usage=disk_usage)


def test_espaco_calcula_percentual_e_junta_saude_do_volume():
    ps = psutil_falso({"C:\\": (1000, 80), "E:\\": (500, 250)})
    r = disco.coletar_espaco(falso({"Get-Volume": [{"Letra": "C", "FileSystemLabel": "SO", "Saude": "Healthy"}]}), ps)
    c = next(i for i in r["itens"] if i["volume"] == "C:")
    assert c["pct_livre"] == 8.0 and c["saude"] == "Healthy" and c["rotulo"] == "SO"
    assert next(i for i in r["itens"] if i["volume"] == "E:")["saude"] == "Desconhecida"


def test_espaco_ignora_cdrom_e_unidade_sem_midia():
    ps = psutil_falso({"C:\\": (1000, 500), "D:\\": (0, 0)})
    r = disco.coletar_espaco(falso({}), ps)
    assert [i["volume"] for i in r["itens"]] == ["C:"]


def test_espaco_sem_psutil_falha_sem_levantar(monkeypatch):
    monkeypatch.setattr(disco, "psutil", None)
    assert disco.coletar_espaco(falso({})) ["ok"] is False


def test_saude_detalhe_smart_sem_admin_marca_precisa_admin():
    r = disco.coletar_saude(falso({
        "Get-PhysicalDisk | Select": [{"FriendlyName": "NVMe", "Tipo": "SSD", "Saude": "Healthy",
                                        "Status": "OK", "Size": 512}],
        "StorageReliabilityCounter": base.ErroConsulta("Access is denied", admin=True)}))
    assert r["ok"] and r["precisa_admin"] and r["itens"][0]["nome"] == "NVMe"


# ------------------------------------------------------------------ eventos
def test_eventos_agrupa_por_fonte_e_id_e_marca_conhecidos():
    brutos = [{"Quando": "2026-09-28T10:00:00", "Id": 41, "ProviderName": "Microsoft-Windows-Kernel-Power",
               "LevelDisplayName": "Crítico", "Msg": "x"}] * 3 + [
              {"Quando": "2026-09-27T10:00:00", "Id": 9, "ProviderName": "Outro", "LevelDisplayName": "Erro", "Msg": "y"}]
    r = eventos.coletar(falso({"Get-WinEvent": brutos}))
    assert r["itens"][0]["quantidade"] == 3 and r["itens"][0]["conhecido"] is True
    assert r["itens"][1]["conhecido"] is False and r["total"] == 4


def test_eventos_sem_nenhum_evento_e_lista_vazia():
    assert eventos.coletar(falso({"Get-WinEvent": ""}))["itens"] == []


# ------------------------------------------------------------------ atualizações
def test_atualizacoes_marca_seguranca_e_dias_pendentes():
    r = atualizacoes.coletar(falso({
        "Search(": [{"Title": "KB1", "Sev": "Critical", "IsDownloaded": True, "Desde": "2026-09-01T00:00:00"},
                    {"Title": "KB2", "Sev": "", "IsDownloaded": False, "Desde": "2026-09-28T00:00:00"}],
        "Win32_QuickFix": {"HotFixID": "KB9", "Em": "2026-09-10T00:00:00"},
        "RebootRequired": {"Pendente": True}}), AGORA)
    assert r["itens"][0]["seguranca"] and r["itens"][0]["dias_pendente"] == 28
    assert not r["itens"][1]["seguranca"]
    assert r["reinicio_pendente"] is True and "KB9" in r["ultimo_instalado"]


def test_atualizacoes_busca_lenta_estourando_tempo_falha_com_motivo():
    r = atualizacoes.coletar(falso({"Search(": base.ErroConsulta("demorou mais de 150 s")}), AGORA)
    assert r["ok"] is False and "150" in r["erro"]


# ------------------------------------------------------------------ winget
TABELA_WINGET = """Name        Id            Version  Available Source
-------------------------------------------------------
Git         Git.Git       2.40.0   2.46.0    winget
Node.js     OpenJS.NodeJS 20.1.0   22.0.0    winget
2 upgrades available.
"""


def test_winget_interpreta_tabela_de_texto():
    itens = winget.interpretar_texto(TABELA_WINGET)
    assert [i["id"] for i in itens] == ["Git.Git", "OpenJS.NodeJS"]
    assert itens[0]["versao_nova"] == "2.46.0"


def test_winget_sem_modulo_cai_para_texto():
    r = winget.coletar(falso({"Get-WinGetPackage": base.ErroConsulta("módulo ausente")}),
                       rodar_texto=lambda: TABELA_WINGET)
    assert r["via"] == "texto" and len(r["itens"]) == 2


def test_winget_com_modulo_usa_o_modulo():
    r = winget.coletar(falso({"Get-WinGetPackage": [{"Name": "Git", "Id": "Git.Git",
                                                    "InstalledVersion": "1", "Nova": "2"}]}))
    assert r["via"] == "modulo" and r["itens"][0]["versao_nova"] == "2"


# ------------------------------------------------------------------ inicialização
def test_inicializacao_le_estado_aprovado_par_e_impar():
    r = inicializacao.coletar(falso({
        "Win32_StartupCommand": [{"Name": "A", "Command": "a.exe", "Location": "HKCU", "User": "x"},
                                 {"Name": "B", "Command": "b.exe", "Location": "HKCU", "User": "x"}],
        "StartupApproved": [{"Nome": "A", "Estado": 2}, {"Nome": "B", "Estado": 3}],
        "Get-ScheduledTask": [{"TaskName": "T", "TaskPath": "\\", "Estado": "Ready"}]}))
    ativo = {i["nome"]: i["ativo"] for i in r["itens"]}
    assert ativo == {"A": True, "B": False} and r["tarefas_no_logon"][0]["nome"] == "T"


# ------------------------------------------------------------------ processos
class ProcFalso:
    def __init__(self, pid, nome, cpu, rss, exe):
        self.pid, self.info, self._cpu, self._rss, self._exe = pid, {"name": nome}, cpu, rss, exe

    def cpu_percent(self, interval=None):
        return self._cpu

    def memory_info(self):
        return types.SimpleNamespace(rss=self._rss)

    def exe(self):
        return self._exe


def test_processos_ordena_por_cpu_limita_topo_e_anexa_assinatura():
    procs = [ProcFalso(i, f"p{i}", float(i), i * 10, f"C:\\p{i}.exe") for i in range(15)]
    mod = types.SimpleNamespace(process_iter=lambda attrs: procs, Error=RuntimeError)
    r = processos.coletar(falso({"Get-AuthenticodeSignature": [
        {"Caminho": "C:\\p14.exe", "Status": "Valid", "Assinante": "CN=Microsoft"}]}),
        mod, dormir=lambda s: None)
    assert len(r["itens"]) == 10 and r["itens"][0]["nome"] == "p14"
    assert r["itens"][0]["assinatura"] == "Valid" and r["itens"][1]["assinatura"] == "Desconhecida"


# ------------------------------------------------------------------ segurança
def test_defender_com_terceiro_lista_o_terceiro_e_ignora_o_proprio_defender():
    r = seguranca.coletar_defender(falso({
        "Get-MpComputerStatus": {"AMServiceEnabled": True, "AntivirusEnabled": False,
                                 "RealTimeProtectionEnabled": False, "AssinaturaEm": "2026-09-20T00:00:00"},
        "Get-MpThreatDetection": base.ErroConsulta("Access is denied", admin=True),
        "AntiVirusProduct": [{"displayName": "Windows Defender"}, {"displayName": "Kaspersky"}]}))
    assert r["antivirus_de_terceiros"] == ["Kaspersky"] and r["precisa_admin"] is True


def test_firewall_converte_texto_em_booleano():
    r = seguranca.coletar_firewall(falso({"Get-NetFirewallProfile": [
        {"Name": "Public", "Ligado": "True", "EntradaPadrao": "Block"},
        {"Name": "Private", "Ligado": "False", "EntradaPadrao": "Block"}]}))
    assert [p["ligado"] for p in r["itens"]] == [True, False]


# ------------------------------------------------------------------ temporários
def _arquivo(pasta, nome, dias, tamanho=10):
    caminho = os.path.join(pasta, nome)
    with open(caminho, "wb") as f:
        f.write(b"x" * tamanho)
    t = time.time() - dias * 86400
    os.utime(caminho, (t, t))
    return caminho


def test_temporarios_so_lista_arquivo_com_mais_de_7_dias(tmp_path):
    velho = _arquivo(str(tmp_path), "velho.tmp", 30, 100)
    _arquivo(str(tmp_path), "novo.tmp", 1, 500)
    r = temporarios.coletar(falso({}), pastas=[("Temporários do usuário", str(tmp_path))],
                            ler_lixeira_fn=lambda: (0, 0))
    assert [c["caminho"] for c in r["candidatos"]] == [velho]
    grupo = r["itens"][0]  # a Lixeira vem depois
    assert grupo["tamanho_bytes"] == 600 and grupo["antigos_bytes"] == 100


def test_temporarios_miniaturas_so_pega_thumbcache(tmp_path):
    _arquivo(str(tmp_path), "thumbcache_256.db", 40, 50)
    _arquivo(str(tmp_path), "outra.dat", 40, 70)
    r = temporarios.coletar(falso({}), pastas=[("Miniaturas", str(tmp_path))],
                            ler_lixeira_fn=lambda: (0, 0))
    assert [os.path.basename(c["caminho"]) for c in r["candidatos"]] == ["thumbcache_256.db"]


def test_temporarios_inclui_lixeira_lida_pela_api(tmp_path):
    r = temporarios.coletar(falso({}), pastas=[], ler_lixeira_fn=lambda: (3, 4096))
    assert r["itens"] == [{"nome": "Lixeira", "pasta": "", "tamanho_bytes": 4096, "arquivos": 3,
                           "antigos_bytes": 0, "truncado": False, "legivel": True}]


def test_temporarios_lixeira_que_nao_responde_e_omitida():
    def falha():
        raise OSError("x")
    assert temporarios.coletar(falso({}), pastas=[], ler_lixeira_fn=falha)["itens"] == []


def test_temporarios_pasta_inexistente_e_ignorada(tmp_path):
    r = temporarios.coletar(falso({}), pastas=[("X", str(tmp_path / "nao_existe"))],
                            ler_lixeira_fn=lambda: (0, 0))
    assert r["ok"] and [i["nome"] for i in r["itens"]] == ["Lixeira"]


def test_temporarios_arquivo_travado_nao_vira_candidato(tmp_path, monkeypatch):
    _arquivo(str(tmp_path), "preso.tmp", 30)
    monkeypatch.setattr(temporarios, "_travado", lambda c: True)
    r = temporarios.coletar(falso({}), pastas=[("Temporários do usuário", str(tmp_path))],
                            ler_lixeira_fn=lambda: (0, 0))
    assert r["candidatos"] == []


# ------------------------------------------------------------------ repositórios
def test_repositorios_interpreta_ahead_sujo_e_sem_upstream():
    a = repositorios.interpretar("# branch.head main\n# branch.upstream origin/main\n# branch.ab +2 -0\n1 .M x")
    assert a["ahead"] == 2 and a["sujo"] is True and a["sem_upstream"] is False
    b = repositorios.interpretar("# branch.head feat\n")
    assert b["sem_upstream"] is True and b["ahead"] == 0


def test_repositorios_acha_repos_e_lista_so_os_pendentes(tmp_path):
    for nome in ("a", "b"):
        os.makedirs(tmp_path / nome / ".git")
    saidas = {str(tmp_path / "a"): "# branch.head main\n# branch.upstream o/m\n# branch.ab +1 -0\n",
              str(tmp_path / "b"): "# branch.head main\n# branch.upstream o/m\n# branch.ab +0 -0\n"}
    r = repositorios.coletar([str(tmp_path)], rodar_git_fn=lambda repo: saidas[repo])
    assert [i["nome"] for i in r["itens"]] == ["a"]


# ------------------------------------------------------------------ drivers e energia
def test_drivers_lista_dispositivos_com_erro():
    r = drivers.coletar(falso({"Win32_PnPEntity": {"Name": "Placa X", "DeviceID": "PCI\\1", "ConfigManagerErrorCode": 28}}))
    assert r["itens"][0]["codigo"] == 28


def test_energia_sem_bateria_e_nao_se_aplica_e_calcula_horas_ligado():
    r = energia.coletar(falso({"LastBootUpTime": {"Desde": "2026-09-29T06:00:00"},
                               "powercfg": {"Plano": "GUID: x (Alto desempenho)"}}), AGORA)
    assert r["tem_bateria"] is False and r["horas_ligado"] == 6.0 and "Alto" in r["plano"]


# ------------------------------------------------------------------ nota
def coletores(**partes):
    return {"coletores": {n: dict({"ok": True, "itens": []}, **v) for n, v in partes.items()}}


def test_pc_saudavel_tira_100():
    r = nota.calcular(coletores(espaco={"itens": [{"volume": "C:", "pct_livre": 40, "saude": "Healthy"}]}))
    assert r["nota"] == 100 and r["descontos"] == []


def test_disco_quase_cheio_desconta_20():
    r = nota.calcular(coletores(espaco={"itens": [{"volume": "C:", "pct_livre": 6, "saude": "Healthy"}]}))
    assert r["nota"] == 80 and r["descontos"][0]["codigo"] == "disco_cheio"


def test_disco_doente_desconta_40():
    r = nota.calcular(coletores(saude={"itens": [{"nome": "HD", "saude": "Warning"}]}))
    assert r["nota"] == 60


def test_defender_desligado_desconta_30_mas_nao_com_antivirus_de_terceiro():
    off = {"itens": [{"antivirus": False, "tempo_real": False}]}
    assert nota.calcular(coletores(defender=off))["nota"] == 70
    assert nota.calcular(coletores(defender=dict(off, antivirus_de_terceiros=["Kaspersky"])))["nota"] == 100


def test_firewall_seguranca_reinicio_driver_e_repos():
    r = nota.calcular(coletores(
        firewall={"itens": [{"perfil": "Public", "ligado": False}]},
        atualizacoes={"itens": [{"seguranca": True, "dias_pendente": 20}], "reinicio_pendente": True},
        drivers={"itens": [{"nome": "x"}]},
        repositorios={"itens": [{"ahead": 1}, {"ahead": 3}, {"ahead": 2}]}))
    pontos = {d["codigo"]: d["pontos"] for d in r["descontos"]}
    assert pontos == {"firewall_desligado": 20, "seguranca_pendente": 15, "reinicio_pendente": 5,
                      "driver_com_erro": 10, "commit_sem_push": 10}
    assert r["nota"] == 40


def test_erro_critico_repetido_e_10_por_fonte_com_teto_20():
    evs = [{"fonte": f"f{i}", "nivel": "Crítico", "quantidade": 3} for i in range(4)]
    evs.append({"fonte": "isolado", "nivel": "Crítico", "quantidade": 1})
    evs.append({"fonte": "comum", "nivel": "Erro", "quantidade": 9})
    r = nota.calcular(coletores(eventos={"itens": evs}))
    assert r["descontos"][0]["pontos"] == 20


def test_atualizacao_recente_de_seguranca_nao_desconta():
    r = nota.calcular(coletores(atualizacoes={"itens": [{"seguranca": True, "dias_pendente": 3}]}))
    assert r["nota"] == 100


def test_coletor_que_falhou_nao_desconta_mas_aparece_em_sem_leitura():
    r = nota.calcular({"coletores": {"firewall": {"ok": False, "itens": [], "erro": "x"}}})
    assert r["nota"] == 100 and r["sem_leitura"] == ["firewall"]


def test_nota_nunca_fica_abaixo_de_zero():
    r = nota.calcular(coletores(
        saude={"itens": [{"nome": "HD", "saude": "Unhealthy"}]},
        defender={"itens": [{"antivirus": False, "tempo_real": False}]},
        firewall={"itens": [{"perfil": "P", "ligado": False}]}))
    assert r["nota"] == 10 and nota.calcular({})["nota"] == 100


# ------------------------------------------------------------------ tendência
def hist(dias_atras, livre, nota_=90, erros=0):
    return {"em": (AGORA - datetime.timedelta(days=dias_atras)).isoformat(),
            "disco_livre_bytes": {"C:": livre}, "nota": nota_, "erros": erros}


def test_dias_para_encher_pelo_ritmo():
    h = [hist(10, 1000), hist(0, 500)]  # perde 50 por dia, restam 500 → 10 dias
    assert tendencia.dias_para_encher(h, "C:", AGORA) == 10.0


def test_disco_que_nao_enche_ou_pouco_historico_da_none():
    assert tendencia.dias_para_encher([hist(10, 500), hist(0, 900)], "C:", AGORA) is None
    assert tendencia.dias_para_encher([hist(0, 500)], "C:", AGORA) is None
    assert tendencia.dias_para_encher([hist(0.2, 600), hist(0, 500)], "C:", AGORA) is None


def test_variacao_de_erros_e_nota_de_7_dias_atras():
    h = [hist(7, 1, nota_=70, erros=2), hist(0, 1, nota_=90, erros=8)]
    assert tendencia.variacao_erros(h, AGORA) == "sobe"
    assert tendencia.nota_ha_7_dias(h, AGORA) == 70


def test_historico_com_linha_quebrada_e_ignorado():
    assert tendencia.dias_para_encher([{"em": "lixo"}, {}], "C:", AGORA) is None


# ------------------------------------------------------------------ resumo
def test_resumo_de_pc_saudavel_diz_que_esta_em_ordem():
    u = coletores(espaco={"itens": [{"volume": "C:", "pct_livre": 50, "saude": "Healthy"}]})
    frases = resumo.resumo_do_dia(u, [], AGORA)
    assert len(frases) == 1 and "em ordem" in frases[0]


def test_resumo_pega_as_tres_piores_e_no_maximo_quatro_frases():
    u = coletores(
        saude={"itens": [{"nome": "HD", "saude": "Warning"}]},
        defender={"itens": [{"antivirus": False, "tempo_real": False}]},
        firewall={"itens": [{"perfil": "P", "ligado": False}]},
        drivers={"itens": [{"nome": "x"}]},
        espaco={"itens": [{"volume": "C:", "pct_livre": 5, "saude": "Healthy"}]})
    frases = resumo.resumo_do_dia(u, [hist(10, 1000), hist(0, 500)], AGORA)
    assert len(frases) <= 4
    assert "disco HD" in frases[0] and "vírus" in frases[1]
    assert not any("driver" in f.lower() or "dispositivo" in f.lower() for f in frases)


def test_resumo_inclui_tendencia_do_disco_quando_cabe():
    u = coletores(espaco={"itens": [{"volume": "C:", "pct_livre": 50, "saude": "Healthy"}]},
                  drivers={"itens": [{"nome": "x"}]})
    frases = resumo.resumo_do_dia(u, [hist(10, 1000), hist(0, 500)], AGORA)
    assert any("enche em cerca de 10 dias" in f for f in frases)


def test_resumo_sem_analise_pede_para_analisar():
    assert "analisar" in resumo.resumo_do_dia(None, [], AGORA)[0]


def test_resumo_avisa_quando_leitura_falhou():
    u = coletores(drivers={"itens": [{"nome": "x"}]})
    u["coletores"]["firewall"] = {"ok": False, "itens": [], "erro": "x"}
    assert any("incompleta" in f for f in resumo.resumo_do_dia(u, [], AGORA))


# ------------------------------------------------------------------ explicações
def test_explicacao_de_evento_conhecido_e_desconhecido():
    assert "desligou sem avisar" in explicacoes.explicar_evento("Microsoft-Windows-Kernel-Power", 41)
    assert "Explicar melhor" in explicacoes.explicar_evento("Qualquer", 1)


# ------------------------------------------------------------------ orquestração
def coletor_ok(itens=None, **extra):
    return lambda: dict({"ok": True, "itens": itens or [], "precisa_admin": False, "erro": ""}, **extra)


def test_analisar_grava_ultima_e_historico_e_sobrevive_a_coletor_quebrado(tmp_path):
    def quebrado():
        raise RuntimeError("boom")
    c = central.Central(str(tmp_path), agora=lambda: AGORA, coletores={
        "espaco": coletor_ok([{"volume": "C:", "livre_bytes": 500, "pct_livre": 50, "saude": "Healthy"}]),
        "drivers": quebrado, "processos": coletor_ok()})
    u = c.analisar()
    assert u["coletores"]["drivers"]["ok"] is False and "RuntimeError" in u["coletores"]["drivers"]["erro"]
    assert c.ultima()["coletado_em"] == AGORA.isoformat(timespec="seconds")
    assert c.historico()[-1]["disco_livre_bytes"] == {"C:": 500} and c.historico()[-1]["nota"] == 100


def test_processos_roda_antes_dos_demais(tmp_path):
    ordem = []
    c = central.Central(str(tmp_path), coletores={
        "espaco": lambda: ordem.append("espaco") or {"ok": True, "itens": []},
        "processos": lambda: ordem.append("processos") or {"ok": True, "itens": []}})
    c.analisar()
    assert ordem[0] == "processos"


def test_segunda_analise_ao_mesmo_tempo_e_recusada(tmp_path):
    c = central.Central(str(tmp_path), coletores={})
    c._trava.acquire()
    assert c.em_andamento and c.analisar() is None
    c._trava.release()


def test_historico_e_cortado_no_limite(tmp_path, monkeypatch):
    monkeypatch.setattr(central, "LIMITE_HISTORICO", 3)
    c = central.Central(str(tmp_path), coletores={"espaco": coletor_ok()})
    for _ in range(5):
        c.analisar()
    assert len(c.historico()) == 3


def test_visao_sem_analise_previa_nao_quebra(tmp_path):
    v = central.Central(str(tmp_path), coletores={}).visao()
    assert v["nota"] is None and "analisar" in v["resumo"][0]


def test_rotina_diaria_so_depois_de_24h(tmp_path):
    relogio = {"t": AGORA}
    c = central.Central(str(tmp_path), agora=lambda: relogio["t"], coletores={"espaco": coletor_ok()})
    assert c.precisa_rotina_diaria() is True
    c.analisar()
    assert c.precisa_rotina_diaria() is False
    relogio["t"] = AGORA + datetime.timedelta(hours=25)
    assert c.precisa_rotina_diaria() is True


def test_ultima_corrompida_e_tratada_como_ausente(tmp_path):
    c = central.Central(str(tmp_path), coletores={})
    with open(c.arquivo_ultima, "w") as f:
        f.write("{corrompido")
    assert c.ultima() is None


# ------------------------------------------------------------------ máscara
def test_mascara_esconde_caminho_de_pasta_protegida_extra():
    dado = {"a": ["C:\\Programas\\Clinica\\prontuarios\\x.db", "C:\\Temp\\ok.tmp"], "n": 3}
    limpo = central.mascarar_para_envio(dado, ["C:\\Programas\\Clinica"])
    assert limpo == {"a": ["[caminho protegido]", "C:\\Temp\\ok.tmp"], "n": 3}
    assert dado["a"][0].startswith("C:")  # o original não é alterado


def test_mascara_sem_extras_devolve_igual():
    assert central.mascarar_para_envio({"a": "b"}, []) == {"a": "b"}


# ------------------------------------------------------------------ limpeza
def ultima_com_candidatos():
    return {"coletores": {"temporarios": {"ok": True, "itens": [
        {"nome": "Temporários do Windows", "tamanho_bytes": 900},
        {"nome": "Lixeira", "tamanho_bytes": 5}], "candidatos": [
        {"caminho": "C:\\Users\\x\\Temp\\pequeno.tmp", "tamanho_bytes": 10, "idade_dias": 9, "grupo": "Temporários do usuário"},
        {"caminho": "C:\\Users\\x\\Temp\\grande.tmp", "tamanho_bytes": 999, "idade_dias": 40, "grupo": "Temporários do usuário"},
        {"caminho": "C:\\Windows\\Temp\\w.tmp", "tamanho_bytes": 5000, "idade_dias": 40, "grupo": "Temporários do Windows"}]}}}


def test_propostas_maior_primeiro_so_quarentena_e_sem_windows_temp():
    p = limpeza.propostas(ultima_com_candidatos())
    assert [x["alvo"] for x in p] == ["C:\\Users\\x\\Temp\\grande.tmp", "C:\\Users\\x\\Temp\\pequeno.tmp"]
    assert all(x["acao"] == "quarentena" and x["por_que_seguro"] for x in p)


def test_propostas_respeitam_limite_e_coletor_falho():
    assert len(limpeza.propostas(ultima_com_candidatos(), limite=1)) == 1
    assert limpeza.propostas({"coletores": {"temporarios": {"ok": False}}}) == []
    assert limpeza.propostas(None) == []


def test_informativos_mostra_windows_temp_sem_propor():
    nomes = [i["nome"] for i in limpeza.informativos(ultima_com_candidatos())]
    assert nomes == ["Temporários do Windows", "Lixeira"]


def test_o_modulo_de_limpeza_nao_importa_motor_nem_executor():
    fonte = open(limpeza.__file__, encoding="utf-8").read()
    codigo = "\n".join(l for l in fonte.splitlines() if l.startswith(("import", "from")))
    assert "aprovacao" not in codigo and "executor" not in codigo
