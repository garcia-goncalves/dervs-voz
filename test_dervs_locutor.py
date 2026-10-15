"""Testes dos perfis de voz (dervs_locutor).

O extrator é falso: devolve um vetor que depende só do "timbre" do trecho (a
frequência do tom puro usado como voz), então nada aqui precisa do modelo nem
de rede. O teste marcado `modelo_real` usa o ERes2Net de verdade e é pulado se
o arquivo não estiver na máquina.
"""
import io
import json
import os

import numpy as np
import pytest

import dervs_config
import dervs_dpapi
import dervs_locutor as L

TAXA = L.TAXA


def voz(freq: float, segundos: float) -> np.ndarray:
    t = np.arange(int(TAXA * segundos)) / TAXA
    return (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def extrator_falso(audio: np.ndarray) -> np.ndarray:
    """Vetor de 8 posições: o espectro grosso do trecho (separa tons diferentes)."""
    esp = np.abs(np.fft.rfft(audio))
    freqs = np.fft.rfftfreq(len(audio), 1 / TAXA)
    faixas = np.array([esp[(freqs >= a) & (freqs < b)].sum() for a, b in
                       [(0, 200), (200, 300), (300, 400), (400, 600), (600, 900),
                        (900, 1500), (1500, 3000), (3000, 8000)]])
    return faixas.astype(np.float32) + 1e-3


@pytest.fixture
def perfis(tmp_path):
    return L.Perfis(str(tmp_path / "vozes"), extrator=extrator_falso)


def test_gravar_cria_perfil_sem_guardar_audio(perfis, tmp_path):
    p = perfis.gravar("André", "dono", voz(250, 16))
    assert (p.nome, p.slug, p.papel, p.ativo) == ("André", "andre", "dono", True)
    arquivos = sorted(os.listdir(tmp_path / "vozes" / "andre"))
    assert arquivos == ["perfil.json", "voz.bin"]
    bruto = (tmp_path / "vozes" / "andre" / "voz.bin").read_bytes()
    with pytest.raises(ValueError):                     # cifrado: não é um .npy legível
        np.load(io.BytesIO(bruto), allow_pickle=False)
    v = np.load(io.BytesIO(dervs_dpapi.desproteger(bruto)), allow_pickle=False)
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-5
    assert json.load(open(tmp_path / "vozes" / "andre" / "perfil.json", encoding="utf-8")) == \
        {"nome": "André", "papel": "dono", "ativo": True}


def test_menos_de_15_segundos_de_fala_e_recusado_com_mensagem_clara(perfis):
    with pytest.raises(L.ErroLocutor, match="15 segundos"):
        perfis.gravar("Ana", "dono", voz(250, 10))
    assert perfis.listar() == []


def test_silencio_nao_conta_como_fala(perfis):
    audio = np.concatenate([voz(250, 8), np.zeros(TAXA * 30, np.float32), voz(250, 4)])
    with pytest.raises(L.ErroLocutor, match="15 segundos"):
        perfis.gravar("Ana", "dono", audio)


def test_janelas_de_3s_e_media(tmp_path):
    chamadas = []

    def espia(a):
        chamadas.append(len(a))
        return extrator_falso(a)
    p = L.Perfis(str(tmp_path), extrator=espia)
    p.gravar("Ana", "convidado", voz(250, 16))
    assert chamadas == [3 * TAXA] * 5          # 16 s -> 5 janelas inteiras de 3 s


def test_papel_invalido(perfis):
    with pytest.raises(L.ErroLocutor, match="papel"):
        perfis.gravar("Ana", "chefe", voz(250, 16))


@pytest.mark.parametrize("nome", ["", "   ", "x" * 41, "a\x00b", "a\nb", "a\x1bb", "../..", "...", "///"])
def test_nome_invalido(perfis, nome):
    with pytest.raises(L.ErroLocutor):
        perfis.gravar(nome, "dono", voz(250, 16))


@pytest.mark.parametrize("nome", ["../fora", "..\\fora", "a/../../b", "C:\\x", "/etc/passwd", "con/../x"])
def test_slug_nunca_escapa_da_pasta(perfis, tmp_path, nome):
    p = perfis.gravar(nome, "dono", voz(250, 16))
    assert "/" not in p.slug and "\\" not in p.slug and ".." not in p.slug
    pasta_vozes = os.path.realpath(tmp_path / "vozes")
    assert os.path.dirname(os.path.realpath(os.path.join(pasta_vozes, p.slug))) == pasta_vozes
    assert os.listdir(tmp_path) == ["vozes"]
    assert perfis.apagar(nome) is True
    assert os.listdir(pasta_vozes) == []


def test_listar_ativar_apagar(perfis, tmp_path):
    perfis.gravar("Ana", "dono", voz(250, 16))
    perfis.gravar("Beto", "convidado", voz(700, 16))
    assert [p.nome for p in perfis.listar()] == ["Ana", "Beto"]
    assert perfis.ativar("Beto", False).ativo is False
    assert [p.ativo for p in perfis.listar()] == [True, False]
    assert perfis.apagar("Ana") is True
    assert not os.path.exists(tmp_path / "vozes" / "ana")
    assert perfis.apagar("Ana") is False
    with pytest.raises(L.ErroLocutor):
        perfis.ativar("Fantasma", True)


def test_listar_ignora_pasta_corrompida(perfis, tmp_path):
    perfis.gravar("Ana", "dono", voz(250, 16))
    ruim = tmp_path / "vozes" / "ruim"
    ruim.mkdir()
    (ruim / "perfil.json").write_text("{nao é json", encoding="utf-8")
    assert [p.nome for p in perfis.listar()] == ["Ana"]


def test_quem_fala_reconhece_e_recusa(perfis):
    perfis.gravar("Ana", "dono", voz(250, 16))
    perfis.gravar("Beto", "convidado", voz(1200, 16))
    p, s = perfis.quem_fala(voz(250, 1.5))
    assert p and p.nome == "Ana" and s > 0.9
    p, s = perfis.quem_fala(voz(1200, 1.5))
    assert p and p.nome == "Beto"
    p, s = perfis.quem_fala(voz(5000, 1.5))          # ninguém cadastrado fala assim
    assert p is None and s < dervs_config.PADRAO["locutor_limiar"]


def test_quem_fala_so_considera_perfis_ativos(perfis):
    perfis.gravar("Ana", "dono", voz(250, 16))
    perfis.ativar("Ana", False)
    assert perfis.quem_fala(voz(250, 1.5)) == (None, 0.0)
    perfis.ativar("Ana", True)
    assert perfis.quem_fala(voz(250, 1.5))[0].nome == "Ana"


def test_quem_fala_usa_limiar_da_config(perfis, monkeypatch):
    perfis.gravar("Ana", "dono", voz(250, 16))
    monkeypatch.setattr(dervs_config, "carregar", lambda: {"locutor_limiar": 1.0})
    p, s = perfis.quem_fala(voz(300, 1.5))
    assert p is None and 0 < s < 1.0


def test_quem_fala_sem_perfis_ou_sem_audio(perfis):
    assert perfis.quem_fala(voz(250, 1)) == (None, 0.0)
    perfis.gravar("Ana", "dono", voz(250, 16))
    assert perfis.quem_fala(np.zeros(0, np.float32)) == (None, 0.0)


def test_pasta_padrao_fica_no_config_dir(tmp_path):
    assert L.Perfis().pasta == os.path.join(dervs_config.CONFIG_DIR, "vozes")


# ------------------------------------------------------------ modelo baixado

def test_modelo_com_hash_certo_nao_baixa(tmp_path):
    (tmp_path / L.MODELO_NOME).write_bytes(b"conteudo")
    import hashlib
    h = hashlib.sha256(b"conteudo").hexdigest()
    assert L.caminho_modelo(baixar=False, pasta=str(tmp_path), sha256=h) == str(tmp_path / L.MODELO_NOME)


def test_modelo_com_hash_errado_e_recusado_sem_baixar(tmp_path):
    (tmp_path / L.MODELO_NOME).write_bytes(b"adulterado")
    assert L.caminho_modelo(baixar=False, pasta=str(tmp_path)) is None


def test_download_com_hash_errado_e_descartado(tmp_path, monkeypatch):
    import io
    monkeypatch.setattr(L.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"lixo"))
    assert L.caminho_modelo(pasta=str(tmp_path)) is None
    assert os.listdir(tmp_path) == []                 # nem o destino nem o .part ficam


def test_download_com_hash_certo_e_gravado_atomicamente(tmp_path, monkeypatch):
    import hashlib
    import io
    monkeypatch.setattr(L.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"modelo"))
    h = hashlib.sha256(b"modelo").hexdigest()
    r = L.caminho_modelo(pasta=str(tmp_path), sha256=h)
    assert r == str(tmp_path / L.MODELO_NOME)
    assert os.listdir(tmp_path) == [L.MODELO_NOME]


def test_download_so_aceita_https(tmp_path):
    assert L.caminho_modelo(pasta=str(tmp_path), url="http://exemplo.com/m.onnx") is None


def test_download_usa_timeout(tmp_path, monkeypatch):
    visto = {}

    def falso(url, timeout=None):
        visto["t"] = timeout
        raise OSError("sem rede")
    monkeypatch.setattr(L.urllib.request, "urlopen", falso)
    assert L.caminho_modelo(pasta=str(tmp_path)) is None
    assert visto["t"]


def test_sem_modelo_nem_rede_gravar_da_erro_claro(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "caminho_modelo", lambda *a, **k: None)
    p = L.Perfis(str(tmp_path))
    assert p.disponivel() is False
    with pytest.raises(L.ErroLocutor, match="modelo"):
        p.gravar("Ana", "dono", voz(250, 16))


# ------------------------------------------------------------ config

def test_config_tem_limiar_e_ligado_por_padrao():
    assert dervs_config.PADRAO["locutor_ligado"] is True
    assert 0.0 <= dervs_config.PADRAO["locutor_limiar"] <= 1.0


@pytest.mark.parametrize("ruim", [-0.1, 1.5, "0.5", None, True, [0.5]])
def test_config_limiar_invalido_volta_ao_padrao(ruim):
    c = dervs_config._validar(dict(dervs_config.PADRAO, locutor_limiar=ruim))
    assert c["locutor_limiar"] == dervs_config.PADRAO["locutor_limiar"]


def test_config_limiar_valido_e_ligado_invalido():
    c = dervs_config._validar(dict(dervs_config.PADRAO, locutor_limiar=1, locutor_ligado="sim"))
    assert c["locutor_limiar"] == 1.0 and isinstance(c["locutor_limiar"], float)
    assert c["locutor_ligado"] is True


# ------------------------------------------------------------ modelo real (opcional)

def test_modelo_real_separa_vozes_diferentes(tmp_path):
    modelo = L.caminho_modelo(baixar=False)
    if not modelo:
        pytest.skip("modelo ERes2Net não está em %LOCALAPPDATA%\\dervs\\modelos")
    ext = L.ExtratorSherpa(modelo)
    a = L._normalizar(ext(voz(120, 3)))
    b = L._normalizar(ext(voz(120, 3)))
    c = L._normalizar(ext(voz(900, 3)))
    assert float(a @ b) > float(a @ c)


def test_voz_npy_em_claro_de_antes_da_cifra_e_lida_e_migrada(perfis, tmp_path):
    perfis.gravar("André", "dono", voz(250, 16))
    d = tmp_path / "vozes" / "andre"
    vetor = np.load(io.BytesIO(dervs_dpapi.desproteger((d / "voz.bin").read_bytes())))
    (d / "voz.bin").unlink()
    np.save(d / "voz.npy", vetor)                       # como gravava a versão anterior
    p, score = perfis.quem_fala(voz(250, 3))
    assert p is not None and p.nome == "André" and score > 0.9
    assert sorted(os.listdir(d)) == ["perfil.json", "voz.bin"]   # migrou e apagou o claro


def test_dpapi_ida_e_volta():
    segredo = b"impressao numerica"
    cifrado = dervs_dpapi.proteger(segredo)
    assert cifrado != segredo and segredo not in cifrado
    assert dervs_dpapi.desproteger(cifrado) == segredo
    with pytest.raises(dervs_dpapi.ErroDpapi):
        dervs_dpapi.desproteger(cifrado[:-4] + b"xxxx")
