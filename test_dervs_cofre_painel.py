"""Cofre no painel: verbo `cofre` da ponte e o laço que mantém o chip e o diário em dia
(critérios 8 e 10 do briefing)."""
import json
import threading

import dervs_cofre as cofre
from test_dervs_ponte_electron import _nova_ponte, _linhas_escritas


def _ultima(processo):
    return json.loads(_linhas_escritas(processo)[-1])


class PonteFalsa:
    def __init__(self):
        self.enviados = []
        self.evento = threading.Event()

    def enviar_cofre(self, notas, pasta):
        self.enviados.append((notas, pasta))
        self.evento.set()


def test_enviar_cofre_manda_contagem_e_pasta():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_cofre(12, r"C:\Users\x\Documentos\DERVS-Cofre")
    assert _ultima(processo) == {"verbo": "cofre", "notas": 12, "pasta": r"C:\Users\x\Documentos\DERVS-Cofre"}


def test_cofre_repetido_nao_e_reenviado_e_antes_de_pronto_nao_manda():
    p, processo = _nova_ponte()
    p.enviar_cofre(1, "C:\\c")
    assert _linhas_escritas(processo) == []
    p._despachar_guardado()
    p.enviar_cofre(1, "C:\\c")
    p.enviar_cofre(1, "C:\\c")
    p.enviar_cofre(2, "C:\\c")
    assert len(_linhas_escritas(processo)) == 2


def test_enviar_cofre_sanea_valores_estranhos():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_cofre(-5, "x" * 5000)
    d = _ultima(processo)
    assert d["notas"] == 0 and len(d["pasta"]) <= 500


def test_laco_manda_a_contagem_do_cofre(tmp_path):
    cv = cofre.Cofre(tmp_path / "c")
    cv.escrever("A", "um")
    cv.escrever("B", "dois")
    ponte, parar = PonteFalsa(), threading.Event()
    cofre.iniciar_loop_cofre(ponte, parar, cv, intervalo=0.01)
    assert ponte.evento.wait(5)
    parar.set()
    assert ponte.enviados[0] == (2, str(cv.raiz))


def test_laco_grava_o_diario_com_os_numeros_do_dia(tmp_path):
    cv = cofre.Cofre(tmp_path / "c")
    ponte, parar = PonteFalsa(), threading.Event()
    cofre.iniciar_loop_cofre(ponte, parar, cv, intervalo=0.01,
                             numeros_fn=lambda: {"ouvidas": 7, "acordadas": 2, "gasto_usd": 0.5})
    assert ponte.evento.wait(5)
    parar.set()
    arquivos = list((cv.raiz / "diario").glob("*.md"))
    assert len(arquivos) == 1
    assert "7" in arquivos[0].read_text(encoding="utf-8")


def test_laco_sobrevive_a_erro_do_cofre(tmp_path):
    class Quebrado:
        raiz = tmp_path

        def reindexar(self):
            raise OSError("disco sumiu")

        def contagem(self):
            raise OSError("disco sumiu")

    ponte, parar = PonteFalsa(), threading.Event()
    t = cofre.iniciar_loop_cofre(ponte, parar, Quebrado(), intervalo=0.01)
    parar.wait(0.2)
    assert t.is_alive()          # nunca deixa o DERVS mudo nem derruba a thread
    parar.set()


# ---------------------------------------------------------------- ligação no motor de voz
class _MotorFalso:
    """Só o que `_tentar_cofre_voz` toca; o método é chamado desligado da classe real."""

    def __init__(self, cv):
        self.cofre = cv
        self.ditos = []
        self.faladas = []
        self.entrada = type("E", (), {"clear": lambda s: self.ditos.append("limpou")})()

    def _diz(self, quem, texto):
        self.ditos.append((quem, texto))

    def _falar_de_thread(self, trabalho):
        self.faladas.append(trabalho())


def _tentar(motor, texto):
    import dervs_electron
    return dervs_electron.Motor._tentar_cofre_voz(motor, texto)


def test_motor_atende_anotar_e_fala(tmp_path):
    cv = cofre.Cofre(tmp_path / "c")
    m = _MotorFalso(cv)
    assert _tentar(m, "DERVS, anota que preciso renovar o certificado") is True
    assert m.faladas == ["Anotei."]
    assert cv.buscar("certificado")


def test_motor_deixa_passar_o_que_nao_e_do_cofre(tmp_path):
    m = _MotorFalso(cofre.Cofre(tmp_path / "c"))
    assert _tentar(m, "me lembra em 10 minutos de tomar água") is False
    assert _tentar(m, "que horas são") is False
    assert m.faladas == []


def test_motor_sem_cofre_nao_atende_nada():
    m = _MotorFalso(None)
    assert _tentar(m, "anota que algo importante") is False


def test_config_cofre_pasta_padrao_e_valor_torto():
    import dervs_config
    assert dervs_config.PADRAO["cofre_pasta"] == ""
    conf = dict(dervs_config.PADRAO)
    conf["cofre_pasta"] = 123
    assert dervs_config._validar(conf)["cofre_pasta"] == ""
    conf["cofre_pasta"] = "x" * 400
    assert dervs_config._validar(conf)["cofre_pasta"] == ""
    conf["cofre_pasta"] = r"D:\Notas"
    assert dervs_config._validar(conf)["cofre_pasta"] == r"D:\Notas"
