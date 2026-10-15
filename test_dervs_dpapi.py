"""Testes da cifra da impressão de voz: DPAPI de verdade (só no Windows) e a migração do
`voz.npy` em claro, que nunca pode derrubar a leitura nem deixar uma impressão sem cifra
para trás por falta de olhar."""
import io
import os
import sys

import numpy as np
import pytest

import dervs_dpapi
import dervs_locutor as L


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI só existe no Windows")
def test_dpapi_real_ida_e_volta_com_dados_binarios_e_grandes():
    for dado in (b"x", bytes(range(256)), os.urandom(200_000)):
        cifrado = dervs_dpapi.proteger(dado)
        assert cifrado != dado and dervs_dpapi.desproteger(cifrado) == dado


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI só existe no Windows")
def test_dpapi_real_recusa_dado_adulterado():
    cifrado = bytearray(dervs_dpapi.proteger(b"impressao numerica"))
    cifrado[len(cifrado) // 2] ^= 0xFF
    with pytest.raises(dervs_dpapi.ErroDpapi):
        dervs_dpapi.desproteger(bytes(cifrado))


@pytest.mark.skipif(sys.platform == "win32", reason="só prova a recusa fora do Windows")
def test_fora_do_windows_a_cifra_recusa_em_vez_de_gravar_em_claro():
    with pytest.raises(dervs_dpapi.ErroDpapi):
        dervs_dpapi.proteger(b"x")


VETOR = np.arange(1, 9, dtype=np.float32)


def _perfil_em_claro(tmp_path, nome="andre", ativo=True):
    d = tmp_path / "vozes" / nome
    d.mkdir(parents=True)
    (d / "perfil.json").write_text(
        '{"nome": "%s", "papel": "dono", "ativo": %s}' % (nome, "true" if ativo else "false"),
        encoding="utf-8")
    np.save(d / "voz.npy", VETOR)
    return d


class _CifraFalsa:
    """Troca a DPAPI por uma cifra reversível qualquer: o teste é da migração, não do Windows."""

    @staticmethod
    def proteger(dados):
        return b"CIFRADO" + bytes(reversed(dados))

    @staticmethod
    def desproteger(dados):
        return bytes(reversed(dados[len(b"CIFRADO"):]))


@pytest.fixture
def cifra_falsa(monkeypatch):
    monkeypatch.setattr(L.dervs_dpapi, "proteger", _CifraFalsa.proteger)
    monkeypatch.setattr(L.dervs_dpapi, "desproteger", _CifraFalsa.desproteger)


def test_migracao_que_falha_na_escrita_ainda_devolve_o_vetor_lido(tmp_path, monkeypatch):
    d = _perfil_em_claro(tmp_path)

    def recusa(dados):
        raise dervs_dpapi.ErroDpapi("recusou")
    monkeypatch.setattr(L.dervs_dpapi, "proteger", recusa)
    vetor = L._ler_voz(str(d))
    assert np.array_equal(vetor, VETOR)                    # a leitura não morre
    assert sorted(os.listdir(d)) == ["perfil.json", "voz.npy"]   # claro fica; nada de .tmp


def test_migracao_com_disco_cheio_nao_deixa_tmp_e_devolve_o_vetor(tmp_path, cifra_falsa,
                                                                  monkeypatch):
    d = _perfil_em_claro(tmp_path)

    def sem_espaco(origem, destino):
        raise OSError("disco cheio")
    monkeypatch.setattr(L.os, "replace", sem_espaco)
    assert np.array_equal(L._ler_voz(str(d)), VETOR)
    assert sorted(os.listdir(d)) == ["perfil.json", "voz.npy"]


def test_migracao_nao_colide_com_tmp_de_outra_thread(tmp_path, cifra_falsa):
    d = _perfil_em_claro(tmp_path)
    (d / "voz.bin.tmp").write_bytes(b"lixo de outra escrita")
    assert np.array_equal(L._ler_voz(str(d)), VETOR)
    assert (d / "voz.bin").exists() and not (d / "voz.npy").exists()
    assert (d / "voz.bin.tmp").read_bytes() == b"lixo de outra escrita"   # não foi pisado


def test_listar_migra_todos_os_perfis_ativos_ou_nao(tmp_path, cifra_falsa):
    ativo = _perfil_em_claro(tmp_path, "andre", ativo=True)
    inativo = _perfil_em_claro(tmp_path, "lia", ativo=False)
    perfis = L.Perfis(str(tmp_path / "vozes"), extrator=lambda a: a)
    assert [p.slug for p in perfis.listar()] == ["andre", "lia"]
    for d in (ativo, inativo):
        assert (d / "voz.bin").exists() and not (d / "voz.npy").exists()
    bruto = _CifraFalsa.desproteger((inativo / "voz.bin").read_bytes())
    assert np.array_equal(np.load(io.BytesIO(bruto), allow_pickle=False), VETOR)


def test_listar_apaga_o_claro_que_sobrou_ao_lado_do_cifrado(tmp_path, cifra_falsa):
    d = _perfil_em_claro(tmp_path)
    (d / "voz.bin").write_bytes(_CifraFalsa.proteger(b"qualquer"))
    L.Perfis(str(tmp_path / "vozes")).listar()
    assert not (d / "voz.npy").exists()


def test_listar_com_migracao_impossivel_ainda_lista(tmp_path, monkeypatch):
    _perfil_em_claro(tmp_path)

    def recusa(dados):
        raise dervs_dpapi.ErroDpapi("recusou")
    monkeypatch.setattr(L.dervs_dpapi, "proteger", recusa)
    assert [p.slug for p in L.Perfis(str(tmp_path / "vozes")).listar()] == ["andre"]
