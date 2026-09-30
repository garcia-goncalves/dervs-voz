"""Testes da supervisão do medidor dos projetos (dervs_vigia_agente)."""
import dervs_vigia_agente as v


class Roda:
    def __init__(self, pids="", tarefa="Running", existe=True):
        self.chamadas = []
        self.pids, self.tarefa, self.existe = pids, tarefa, existe

    def __call__(self, args, timeout=20):
        self.chamadas.append(args)
        texto = " ".join(args)
        if "Get-CimInstance" in texto:
            return 0, self.pids
        if "/Query" in texto:
            return (0, "Status\n%s\n" % self.tarefa) if self.existe else (1, "")
        if "/Run" in texto:
            return 0, "SUCESSO"
        return 1, ""

    def rodou_a_tarefa(self):
        return any("/Run" in " ".join(a) for a in self.chamadas)


def test_um_processo_esta_tudo_certo_e_nao_mexe_em_nada():
    r = Roda(pids="9124\n")
    assert v.VigiaAgente(executar=r).verificar() == {"processos": 1, "acao": "nada"}
    assert not r.rodou_a_tarefa()


def test_nenhum_processo_religa_a_tarefa_existente():
    r = Roda(pids="", tarefa="Ready")
    res = v.VigiaAgente(executar=r).verificar()
    assert res == {"processos": 0, "acao": "religou"} and r.rodou_a_tarefa()


def test_nenhum_processo_mas_tarefa_rodando_espera_sem_duplicar():
    r = Roda(pids="", tarefa="Running")
    res = v.VigiaAgente(executar=r).verificar()
    assert res["acao"] == "nada" and not r.rodou_a_tarefa()


def test_sem_a_tarefa_agendada_nao_inventa_outra():
    r = Roda(pids="", existe=False)
    res = v.VigiaAgente(executar=r).verificar()
    assert res["acao"] == "sem_tarefa" and not r.rodou_a_tarefa()


def test_dois_processos_so_avisa_e_nunca_mata():
    r = Roda(pids="1\n2\n")
    res = v.VigiaAgente(executar=r).verificar()
    assert res == {"processos": 2, "acao": "duplicado"}
    assert not any("Stop" in " ".join(a) or "taskkill" in " ".join(a) for a in r.chamadas)


def test_nao_religa_mais_de_uma_vez_a_cada_10_minutos():
    t = [0.0]
    r = Roda(pids="", tarefa="Ready")
    vigia = v.VigiaAgente(executar=r, relogio=lambda: t[0])
    assert vigia.verificar()["acao"] == "religou"
    t[0] = 60
    assert vigia.verificar()["acao"] == "espera"
    t[0] = 700
    assert vigia.verificar()["acao"] == "religou"


def test_falha_do_sistema_nao_levanta():
    def quebra(args, timeout=20):
        raise OSError("sem powershell")
    assert v.VigiaAgente(executar=quebra).verificar()["acao"] == "indisponivel"


def test_loop_avisa_so_quando_ha_o_que_avisar():
    import threading
    parar = threading.Event()
    vistos = []

    class Falso:
        def __init__(self):
            self.n = 0

        def verificar(self):
            self.n += 1
            return {"processos": 1, "acao": "nada"} if self.n == 1 else \
                {"processos": 0, "acao": "religou"}

    def ao(r):
        vistos.append(r)
        parar.set()

    t = v.iniciar_loop(parar, ao, intervalo_s=0.01, vigia=Falso())
    t.join(3)
    assert [r["acao"] for r in vistos] == ["religou"]
