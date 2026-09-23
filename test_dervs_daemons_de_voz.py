#!/usr/bin/env python3
"""Os três daemons de voz (Kokoro, Piper, XTTS) falam o mesmo protocolo de
linha com o `dervs_tts.py`:

    READY            ao terminar de carregar
    WAV <caminho>    uma por frase (Kokoro/Piper) ou uma por pedido (XTTS)
    FIM              fim do pedido (Kokoro/Piper)
    ERRO <motivo>    o pedido falhou — o daemon NÃO morre por causa disso

Antes deste arquivo eles não tinham teste próprio: uma quebra dentro deles
(protocolo, cerca de erro, gravação do wav) só apareceria com o DERVS mudo.

As bibliotecas pesadas (kokoro_onnx, piper, TTS/torch) são trocadas por
dublês em `sys.modules` — o que se testa é o protocolo e a gravação do wav,
não a qualidade da voz. Cada daemon é importado do zero em cada teste.

Rodar: python -m pytest test_dervs_daemons_de_voz.py -q
"""
import importlib
import io
import json
import os
import sys
import types
import wave

import pytest

np = pytest.importorskip("numpy", reason="os daemons de voz precisam de numpy")


# ---- infraestrutura -------------------------------------------------------

def _importar_do_zero(monkeypatch, nome, modulos_falsos):
    """Importa `nome` com `modulos_falsos` no lugar das bibliotecas pesadas."""
    for chave, modulo in modulos_falsos.items():
        monkeypatch.setitem(sys.modules, chave, modulo)
    monkeypatch.delitem(sys.modules, nome, raising=False)
    return importlib.import_module(nome)


def _rodar(monkeypatch, modulo, pedidos, argv=None):
    """Roda `modulo.main()` com `pedidos` (lista de linhas) no stdin e devolve
    as linhas escritas no stdout. Acabar o stdin é o app saindo."""
    entrada = "".join(l if l.endswith("\n") else l + "\n" for l in pedidos)
    saida = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(entrada))
    monkeypatch.setattr(sys, "stdout", saida)
    monkeypatch.setattr(sys, "argv", argv or ["daemon"])
    modulo.main()
    return saida.getvalue().splitlines()


@pytest.fixture(autouse=True)
def _wavs_no_tmp(tmp_path, monkeypatch):
    """Os wavs que os daemons gravam vão para a pasta do teste."""
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))


# ---- Kokoro ---------------------------------------------------------------

class _KokoroFalso:
    chamadas = []
    falha_em = None      # frase que faz `create` explodir

    def __init__(self, modelo, vozes):
        self.modelo, self.vozes = modelo, vozes

    def create(self, frase, voice, speed, lang):
        _KokoroFalso.chamadas.append((frase, voice, speed, lang))
        if _KokoroFalso.falha_em and _KokoroFalso.falha_em in frase:
            raise RuntimeError("voz quebrou")
        return np.full(2400, 0.5, dtype=np.float32), 24000


@pytest.fixture
def kokoro(monkeypatch):
    _KokoroFalso.chamadas = []
    _KokoroFalso.falha_em = None
    falso = types.ModuleType("kokoro_onnx")
    falso.Kokoro = _KokoroFalso
    return _importar_do_zero(monkeypatch, "dervs_kokoro_daemon",
                             {"kokoro_onnx": falso})


def test_kokoro_frases_quebra_em_pontuacao_e_ignora_vazio(kokoro):
    assert kokoro._frases("Oi. Tudo bem? Sim; claro!") == [
        "Oi.", "Tudo bem?", "Sim;", "claro!"]
    assert kokoro._frases("   ") == []
    assert kokoro._frases("sem pontuacao") == ["sem pontuacao"]


def test_kokoro_dir_modelos_respeita_a_variavel_de_ambiente(kokoro, monkeypatch):
    monkeypatch.setenv("DERVS_MODELOS", r"C:\meus\modelos")
    assert kokoro._dir_modelos() == r"C:\meus\modelos"


def test_kokoro_gravar_wav_faz_um_wav_int16_mono_com_silencio_no_fim(kokoro):
    caminho = kokoro._gravar_wav(np.full(2400, 0.5, dtype=np.float32), 24000)
    with wave.open(caminho, "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
        esperado = 2400 + int(24000 * kokoro.SILENCIO_ENTRE_FRASES_S)
        assert w.getnframes() == esperado
        amostras = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    assert amostras[0] == int(0.5 * 32767)
    assert amostras[-1] == 0            # a pausa entre frases é silêncio


def test_kokoro_gravar_wav_nunca_estoura_o_int16(kokoro):
    caminho = kokoro._gravar_wav(np.array([5.0, -5.0], dtype=np.float32), 100)
    with wave.open(caminho, "rb") as w:
        amostras = np.frombuffer(w.readframes(2), dtype=np.int16)
    assert list(amostras) == [32767, -32767]


def test_kokoro_protocolo_ready_um_wav_por_frase_e_fim(kokoro, monkeypatch):
    linhas = _rodar(monkeypatch, kokoro,
                    [json.dumps({"texto": "Oi. Tudo bem?"})])
    assert linhas[0] == "READY"
    assert [l.split()[0] for l in linhas[1:]] == ["WAV", "WAV", "FIM"]
    for l in linhas[1:3]:
        assert os.path.isfile(l[len("WAV "):])
    assert [c[0] for c in _KokoroFalso.chamadas] == ["Oi.", "Tudo bem?"]


def test_kokoro_usa_os_padroes_e_respeita_o_que_o_pedido_manda(kokoro, monkeypatch):
    _rodar(monkeypatch, kokoro, [
        json.dumps({"texto": "a"}),
        json.dumps({"texto": "b", "voz": "pm_alex", "speed": 1.3, "lang": "pt-pt"}),
    ])
    assert _KokoroFalso.chamadas == [
        ("a", kokoro.VOZ_PADRAO, 1.0, kokoro.LANG_PADRAO),
        ("b", "pm_alex", 1.3, "pt-pt"),
    ]


@pytest.mark.parametrize("pedido", ["isso nao e json", json.dumps({"sem": "texto"})])
def test_kokoro_pedido_ruim_vira_erro_e_o_daemon_continua(kokoro, monkeypatch, pedido):
    linhas = _rodar(monkeypatch, kokoro, [pedido, json.dumps({"texto": "ok"})])
    assert linhas[0] == "READY"
    assert linhas[1].startswith("ERRO ")
    assert linhas[-2].startswith("WAV ") and linhas[-1] == "FIM"


def test_kokoro_falha_no_meio_do_pedido_manda_erro_sem_fim(kokoro, monkeypatch):
    _KokoroFalso.falha_em = "Segunda"
    linhas = _rodar(monkeypatch, kokoro,
                    [json.dumps({"texto": "Primeira. Segunda. Terceira."})])
    assert linhas[0] == "READY"
    assert linhas[1].startswith("WAV ")     # a 1ª frase já tinha saído
    assert linhas[2] == "ERRO voz quebrou"
    assert "FIM" not in linhas


def test_kokoro_linhas_em_branco_sao_ignoradas(kokoro, monkeypatch):
    assert _rodar(monkeypatch, kokoro, ["", "   ", ""]) == ["READY"]


def test_kokoro_modelo_que_nao_carrega_avisa_e_sai_sem_ready(monkeypatch, capsys):
    class _Quebra:
        def __init__(self, *a):
            raise FileNotFoundError("sem modelo\nem lugar nenhum")

    falso = types.ModuleType("kokoro_onnx")
    falso.Kokoro = _Quebra
    modulo = _importar_do_zero(monkeypatch, "dervs_kokoro_daemon", {"kokoro_onnx": falso})
    linhas = _rodar(monkeypatch, modulo, [json.dumps({"texto": "oi"})])
    assert len(linhas) == 1
    assert linhas[0].startswith("ERRO carga do modelo: ")
    assert "\n" not in linhas[0][len("ERRO "):]
    assert "falha ao carregar modelo" in capsys.readouterr().err


# ---- Piper ----------------------------------------------------------------

class _ChunkFalso:
    sample_rate = 22050
    sample_channels = 1
    sample_width = 2

    def __init__(self, n=1000):
        self.audio_int16_array = np.full(n, 1000, dtype=np.int16)


class _VozPiperFalsa:
    carregadas = []
    sinteses = []

    @classmethod
    def load(cls, caminho):
        cls.carregadas.append(caminho)
        if "quebrado" in caminho:
            raise OSError("modelo corrompido")
        return cls()

    def synthesize(self, texto, cfg):
        _VozPiperFalsa.sinteses.append((texto, cfg))
        if texto == "explode":
            raise RuntimeError("sintese falhou")
        for _ in texto.split("|"):           # "|" separa frases no dublê
            yield _ChunkFalso()


class _ConfigFalsa:
    def __init__(self, length_scale=None, noise_w_scale=None):
        self.length_scale, self.noise_w_scale = length_scale, noise_w_scale


@pytest.fixture
def piper(monkeypatch):
    _VozPiperFalsa.carregadas = []
    _VozPiperFalsa.sinteses = []
    pacote = types.ModuleType("piper")
    pacote.PiperVoice = _VozPiperFalsa
    config = types.ModuleType("piper.config")
    config.SynthesisConfig = _ConfigFalsa
    pacote.config = config
    return _importar_do_zero(monkeypatch, "dervs_piper_daemon",
                             {"piper": pacote, "piper.config": config})


def test_piper_gravar_wav_copia_o_formato_do_chunk_e_cola_silencio(piper):
    caminho = piper._gravar_wav(_ChunkFalso(1000))
    with wave.open(caminho, "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 22050)
        assert w.getnframes() == 1000 + int(22050 * piper.SILENCIO_ENTRE_FRASES_S)


def test_piper_carrega_o_modelo_uma_vez_so(piper, monkeypatch):
    _rodar(monkeypatch, piper, [
        json.dumps({"texto": "a"}), json.dumps({"texto": "b"}),
    ], argv=["daemon", "voz.onnx"])
    assert _VozPiperFalsa.carregadas == ["voz.onnx"]       # aquece 1x, reusa


def test_piper_protocolo_ready_um_wav_por_frase_e_fim(piper, monkeypatch):
    linhas = _rodar(monkeypatch, piper, [json.dumps({"texto": "um|dois|tres"})],
                    argv=["daemon", "voz.onnx"])
    assert linhas[0] == "READY"
    assert [l.split()[0] for l in linhas[1:]] == ["WAV", "WAV", "WAV", "FIM"]


def test_piper_repassa_ritmo_e_ruido_do_pedido(piper, monkeypatch):
    _rodar(monkeypatch, piper, [json.dumps(
        {"texto": "x", "length_scale": 0.95, "noise_w": 0.9})],
        argv=["daemon", "voz.onnx"])
    cfg = _VozPiperFalsa.sinteses[0][1]
    assert (cfg.length_scale, cfg.noise_w_scale) == (0.95, 0.9)


def test_piper_o_modelo_do_pedido_vence_o_padrao(piper, monkeypatch):
    _rodar(monkeypatch, piper, [json.dumps({"texto": "x", "modelo": "outra.onnx"})],
           argv=["daemon", "voz.onnx"])
    assert _VozPiperFalsa.carregadas == ["voz.onnx", "outra.onnx"]


def test_piper_sem_nenhum_modelo_vira_erro_claro(piper, monkeypatch):
    linhas = _rodar(monkeypatch, piper, [json.dumps({"texto": "x"})])
    assert linhas == ["READY", "ERRO nenhum modelo informado"]


def test_piper_modelo_padrao_quebrado_avisa_mas_sobe(piper, monkeypatch, capsys):
    linhas = _rodar(monkeypatch, piper, [], argv=["daemon", "quebrado.onnx"])
    assert linhas == ["READY"]
    assert "falha ao carregar quebrado.onnx" in capsys.readouterr().err


def test_piper_sintese_que_falha_vira_erro_e_o_daemon_continua(piper, monkeypatch):
    linhas = _rodar(monkeypatch, piper, [
        json.dumps({"texto": "explode"}), "lixo", json.dumps({"texto": "ok"}),
    ], argv=["daemon", "voz.onnx"])
    assert linhas[0] == "READY"
    assert linhas[1] == "ERRO sintese falhou"
    assert linhas[2].startswith("ERRO ")            # a linha "lixo"
    assert linhas[-2].startswith("WAV ") and linhas[-1] == "FIM"


# ---- XTTS -----------------------------------------------------------------

class _TTSFalso:
    ditos = []

    def __init__(self, nome):
        self.nome = nome

    def tts_to_file(self, text, speaker, language, file_path):
        _TTSFalso.ditos.append((text, speaker, language))
        if text == "explode":
            raise RuntimeError("torch caiu")
        with open(file_path, "wb") as f:
            f.write(b"RIFF")


@pytest.fixture
def xtts(monkeypatch):
    _TTSFalso.ditos = []
    api = types.ModuleType("TTS.api")
    api.TTS = _TTSFalso
    pacote = types.ModuleType("TTS")
    pacote.api = api
    # `torch` real (se existir) não deve ser carregado por um teste de protocolo
    monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))
    return _importar_do_zero(monkeypatch, "dervs_tts_daemon",
                             {"TTS": pacote, "TTS.api": api})


def test_xtts_protocolo_ready_e_um_wav_por_pedido(xtts, monkeypatch):
    linhas = _rodar(monkeypatch, xtts, [json.dumps("bom dia")])
    assert linhas[0] == "READY"
    assert linhas[1].startswith("WAV ")
    assert os.path.isfile(linhas[1][len("WAV "):])
    assert _TTSFalso.ditos == [("bom dia", xtts.FALANTE, xtts.IDIOMA)]


def test_xtts_aceita_texto_cru_sem_aspas_de_json(xtts, monkeypatch):
    _rodar(monkeypatch, xtts, ["oi sem aspas"])
    assert _TTSFalso.ditos[0][0] == "oi sem aspas"


def test_xtts_erro_na_sintese_devolve_erro_e_continua(xtts, monkeypatch):
    linhas = _rodar(monkeypatch, xtts, [json.dumps("explode"), json.dumps("ok")])
    assert linhas[0] == "READY"
    assert linhas[1] == "ERRO"
    assert linhas[2].startswith("WAV ")


def test_xtts_falante_e_idioma_vem_do_ambiente(monkeypatch):
    monkeypatch.setenv("DERVS_XTTS_SPEAKER", "Outra Pessoa")
    monkeypatch.setenv("DERVS_XTTS_LANG", "en")
    api = types.ModuleType("TTS.api")
    api.TTS = _TTSFalso
    pacote = types.ModuleType("TTS")
    pacote.api = api
    monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))
    modulo = _importar_do_zero(monkeypatch, "dervs_tts_daemon",
                               {"TTS": pacote, "TTS.api": api})
    assert (modulo.FALANTE, modulo.IDIOMA) == ("Outra Pessoa", "en")
