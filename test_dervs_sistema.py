#!/usr/bin/env python3
"""Testa a leitura de CPU/RAM/disco sem precisar medir a máquina de verdade —
um dublê de `psutil` (ver `dervs_sistema.py`, `coletar_stats`) e uma `ponte`
de mentira que só guarda o que recebeu.

Rodar: python -m pytest test_dervs_sistema.py -q
"""
import threading

import dervs_sistema as sistema


class DiscoFalso:
    def __init__(self, livre_bytes, total_bytes):
        self.free = livre_bytes
        self.total = total_bytes


class MemoriaFalsa:
    def __init__(self, percent):
        self.percent = percent


class PsutilFalso:
    def __init__(self, cpu=42.0, ram=55.5, livre_gb=100.0, total_gb=500.0):
        self._cpu = cpu
        self._mem = MemoriaFalsa(ram)
        self._disco = DiscoFalso(livre_gb * 1024 ** 3, total_gb * 1024 ** 3)

    def cpu_percent(self, interval=None):
        return self._cpu

    def virtual_memory(self):
        return self._mem

    def disk_usage(self, caminho):
        return self._disco


class PonteFalsa:
    def __init__(self):
        self.chamadas = []

    def enviar_sistema(self, cpu, ram, disco_livre_gb, disco_total_gb):
        self.chamadas.append({
            "cpu": cpu, "ram": ram,
            "disco_livre_gb": disco_livre_gb, "disco_total_gb": disco_total_gb,
        })


# ---- coletar_stats -----------------------------------------------------

def test_coletar_stats_le_cpu_ram_disco_do_psutil_injetado():
    fake = PsutilFalso(cpu=17.3, ram=61.0, livre_gb=120.4, total_gb=512.0)
    stats = sistema.coletar_stats(caminho_disco="C:\\", modulo_psutil=fake)
    assert stats == {"cpu": 17.3, "ram": 61.0, "disco_livre_gb": 120.4, "disco_total_gb": 512.0}


def test_coletar_stats_arredonda_em_uma_casa():
    fake = PsutilFalso(cpu=17.333, ram=61.049, livre_gb=120.44, total_gb=512.01)
    stats = sistema.coletar_stats(caminho_disco="C:\\", modulo_psutil=fake)
    assert stats["cpu"] == 17.3
    assert stats["ram"] == 61.0


def test_coletar_stats_sem_psutil_devolve_none():
    assert sistema.coletar_stats(caminho_disco="C:\\", modulo_psutil=None) is None


def test_coletar_stats_grampeia_entre_0_e_100():
    fake = PsutilFalso(cpu=-5.0, ram=250.0)
    stats = sistema.coletar_stats(caminho_disco="C:\\", modulo_psutil=fake)
    assert stats["cpu"] == 0.0
    assert stats["ram"] == 100.0


def test_coletar_stats_disco_com_erro_devolve_none():
    class PsutilQueQuebra(PsutilFalso):
        def disk_usage(self, caminho):
            raise OSError("disco nao existe")
    stats = sistema.coletar_stats(caminho_disco="Z:\\", modulo_psutil=PsutilQueQuebra())
    assert stats is None


# ---- _um_passo -----------------------------------------------------------

def test_um_passo_manda_os_stats_pela_ponte():
    ponte = PonteFalsa()
    coletar = lambda: {"cpu": 1.0, "ram": 2.0, "disco_livre_gb": 3.0, "disco_total_gb": 4.0}
    ok = sistema._um_passo(ponte, coletar=coletar)
    assert ok is True
    assert ponte.chamadas == [{"cpu": 1.0, "ram": 2.0, "disco_livre_gb": 3.0, "disco_total_gb": 4.0}]


def test_um_passo_sem_dado_nao_manda_nada_e_devolve_false():
    ponte = PonteFalsa()
    ok = sistema._um_passo(ponte, coletar=lambda: None)
    assert ok is False
    assert ponte.chamadas == []


# ---- iniciar_loop_sistema -------------------------------------------------

def test_loop_manda_varias_vezes_ate_o_evento_de_parar():
    ponte = PonteFalsa()
    parar = threading.Event()
    contador = {"n": 0}

    def coletar():
        contador["n"] += 1
        if contador["n"] >= 3:
            parar.set()
        return {"cpu": 1.0, "ram": 1.0, "disco_livre_gb": 1.0, "disco_total_gb": 1.0}

    t = sistema.iniciar_loop_sistema(ponte, parar, intervalo=0.01, coletar=coletar)
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert len(ponte.chamadas) == 3


def test_loop_sem_psutil_avisa_uma_vez_so(capsys):
    ponte = PonteFalsa()
    parar = threading.Event()
    contador = {"n": 0}

    def coletar():
        contador["n"] += 1
        if contador["n"] >= 4:
            parar.set()
        return None

    t = sistema.iniciar_loop_sistema(ponte, parar, intervalo=0.01, coletar=coletar)
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert ponte.chamadas == []
    saida = capsys.readouterr()
    assert saida.err.count("psutil nao instalado") == 1
