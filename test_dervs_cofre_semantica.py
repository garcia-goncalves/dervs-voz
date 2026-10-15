"""Busca por significado no cofre (`dervs_cofre_semantica`): lógica provada com um embedder FALSO e
determinístico (sem baixar modelo) e UM teste real, que pula sem o pacote ou sem o modelo em disco."""
import sqlite3
import time

import numpy as np
import pytest

import dervs_cofre as cofre
import dervs_cofre_semantica as sem
import dervs_cofre_voz as voz

# conceitos do embedder falso: cada grupo de palavras vira um eixo (sinônimos caem no mesmo eixo)
CONCEITOS = [
    {"dentista", "odontologica", "odontologico", "dente", "dentes"},
    {"carro", "automovel", "oficina", "mecanica"},
    {"servidor", "hospedagem", "vps", "ovh"},
    {"remedio", "farmacia", "analgesico"},
    {"viagem", "passagem", "hotel", "praia"},
]


class Falso:
    """Embedder determinístico: bolsa de conceitos. Conta quantos textos já embutiu."""
    modelo = "falso-v1"

    def __init__(self, carregado=True, quebra=False):
        self._carregado = carregado
        self.quebra = quebra
        self.embutidos = 0
        self.aquecido = 0
        self.ultimo_uso = 0.0
        self.liberado = 0

    def pronto(self):
        return True

    def carregado(self):
        return self._carregado

    def aquecer(self):
        self.aquecido += 1
        self._carregado = True
        return True

    def embutir(self, textos):
        if self.quebra:
            raise RuntimeError("modelo quebrado")
        self.ultimo_uso = time.monotonic()
        saida = []
        for t in textos:
            self.embutidos += 1
            v = np.zeros(len(CONCEITOS) + 1, dtype=np.float32)
            for p in cofre._norm(t).replace("\n", " ").split():
                p = p.strip(".,;:!?-")
                for i, grupo in enumerate(CONCEITOS):
                    if p in grupo:
                        v[i] += 1.0
            v[-1] = 0.0
            n = np.linalg.norm(v)
            saida.append(v / n if n else v)
        return np.array(saida, dtype=np.float32)

    def liberar(self):
        self._carregado = False
        self.liberado += 1


def _nota(cv, rel, titulo, corpo, extra=""):
    caminho = cv.raiz / rel
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(f"---\ntitulo: {titulo}\n{extra}---\n{corpo}\n", encoding="utf-8")
    return caminho


@pytest.fixture
def cv(tmp_path):
    c = cofre.Cofre(tmp_path / "cofre", semantica=True, embedder=Falso())
    _nota(c, "entrada/consulta.md", "Consulta odontológica", "Marcada para terça às 15h, levar exames.")
    _nota(c, "entrada/oficina.md", "Oficina", "O automóvel precisa de revisão mecânica.")
    _nota(c, "entrada/ovh.md", "Servidor novo", "Decidi migrar a hospedagem para a OVH.")
    c.reindexar()
    return c


# ------------------------------------------------------------- degradação silenciosa
def test_desligada_por_padrao_e_igual_a_antes(tmp_path):
    c = cofre.Cofre(tmp_path / "c")
    _nota(c, "entrada/a.md", "Consulta odontológica", "terça")
    c.reindexar()
    assert c.semantica_disponivel() is False
    assert c.buscar_hibrido("dentista") == c.buscar("dentista") == []
    assert c.indexar_vetores() == 0
    assert c.vetorizar_em_fundo() is None
    assert not (c.pasta_indice / "vetores.sqlite").exists()


def test_sem_o_pacote_nada_levanta(tmp_path, monkeypatch):
    monkeypatch.setattr(sem, "pacote_instalado", lambda: False)
    c = cofre.Cofre(tmp_path / "c", semantica=True)           # embedder real, pacote "ausente"
    _nota(c, "entrada/a.md", "Servidor", "hospedagem OVH")
    c.reindexar()
    assert c.semantica_disponivel() is False
    assert c.indexar_vetores() == 0
    assert [a["caminho"] for a in c.buscar_hibrido("servidor")] == ["entrada/a.md"]


def test_modelo_ausente_sem_download_liberado_nao_esta_disponivel(tmp_path):
    emb = sem.EmbedderFastembed(pasta=tmp_path / "vazio", baixar=False)
    assert emb.pronto() is False or not sem.pacote_instalado()
    assert not emb.carregado()


def test_embedder_quebrado_degrada_em_silencio(cv):
    cv._embedder.quebra = True
    assert cv.indexar_vetores() == 0
    assert [a["caminho"] for a in cv.buscar_hibrido("servidor")] == ["entrada/ovh.md"]


# ------------------------------------------------------------- vetores incrementais
def test_vetoriza_so_o_que_e_novo_ou_mudou(cv):
    assert cv.indexar_vetores() == 3
    assert (cv.pasta_indice / "vetores.sqlite").exists()
    assert cv._embedder.embutidos == 3
    assert cv.indexar_vetores() == 0                    # nada mudou: nenhum cálculo
    assert cv._embedder.embutidos == 3
    p = _nota(cv, "entrada/oficina.md", "Oficina", "O carro quebrou de novo.")
    p.touch()
    cv.reindexar()
    assert cv.indexar_vetores() == 1
    assert cv._embedder.embutidos == 4


def test_nota_apagada_perde_o_vetor(cv):
    cv.indexar_vetores()
    (cv.raiz / "entrada" / "oficina.md").unlink()
    cv.reindexar()
    cv.indexar_vetores()
    con = sqlite3.connect(cv.pasta_indice / "vetores.sqlite")
    assert sorted(c for (c,) in con.execute("SELECT caminho FROM vetores")) == ["entrada/consulta.md", "entrada/ovh.md"]
    con.close()


def test_vetor_guardado_como_float32(cv):
    cv.indexar_vetores()
    con = sqlite3.connect(cv.pasta_indice / "vetores.sqlite")
    dim, blob = con.execute("SELECT dim, vec FROM vetores LIMIT 1").fetchone()
    con.close()
    assert len(blob) == dim * 4


def test_trocar_de_modelo_revetoriza(cv):
    cv.indexar_vetores()
    cv._embedder.modelo = "falso-v2"
    assert cv.indexar_vetores() == 3


# ------------------------------------------------------------- busca híbrida
def test_acha_por_significado_o_que_palavra_nenhuma_acharia(cv):
    cv.indexar_vetores()
    assert cv.buscar("dentista") == []                   # FTS sozinho não vê
    achados = cv.buscar_hibrido("dentista")
    assert [a["caminho"] for a in achados] == ["entrada/consulta.md"]
    assert achados[0]["por"] == "significado"
    assert achados[0]["titulo"] == "Consulta odontológica" and achados[0]["trecho"]


def test_achado_pelos_dois_caminhos_vem_primeiro(cv):
    _nota(cv, "entrada/outra.md", "Compras", "levar o dentista ao mercado")   # só palavra "dentista"
    cv.reindexar()
    cv.indexar_vetores()
    achados = cv.buscar_hibrido("dentista")
    assert achados[0]["caminho"] == "entrada/outra.md" and achados[0]["por"] == "ambos"
    assert {a["caminho"] for a in achados} == {"entrada/outra.md", "entrada/consulta.md"}


def test_pergunta_sem_parentesco_nao_traz_nota_so_por_semantica(cv):
    cv.indexar_vetores()
    assert cv.buscar_hibrido("xadrez com meu avô") == []


def test_modelo_nao_carregado_nao_bloqueia_a_voz(cv):
    cv.indexar_vetores()
    cv._embedder._carregado = False
    achados = cv.buscar_hibrido("servidor")
    assert [a["caminho"] for a in achados] == ["entrada/ovh.md"]        # só palavras, na hora
    for _ in range(50):
        if cv._embedder.aquecido:
            break
        time.sleep(0.02)
    assert cv._embedder.aquecido == 1                                    # e aquece em fundo


def test_limite_respeitado(cv):
    cv.indexar_vetores()
    assert len(cv.buscar_hibrido("servidor carro dentista", limite=2)) <= 2


def test_buscar_continua_igual(cv):
    cv.indexar_vetores()
    assert [a["caminho"] for a in cv.buscar("servidor")] == ["entrada/ovh.md"]
    assert set(cv.buscar("servidor")[0]) == {"caminho", "titulo", "privado", "trecho"}


def test_fusao_rrf():
    assert sem.fundir_rrf(["a", "b", "c"], ["c", "d"])[:2] == ["c", "a"]
    assert sem.fundir_rrf([], []) == []


# ------------------------------------------------------------- privacidade
def test_privada_achada_por_significado_continua_privada(cv):
    _nota(cv, "privado/saude.md", "Saúde", "consulta com o dentista na terça")
    cv.reindexar()
    cv.indexar_vetores()
    achados = cv.buscar_hibrido("dentista")
    priv = [a for a in achados if a["caminho"] == "privado/saude.md"]
    assert priv and priv[0]["privado"] is True
    con = sqlite3.connect(cv.pasta_indice / "vetores.sqlite")
    assert con.execute("SELECT privado FROM vetores WHERE caminho='privado/saude.md'").fetchone() == (1,)
    con.close()


def test_etiqueta_privado_tambem_marca_no_indice_vetorial(cv):
    _nota(cv, "entrada/x.md", "Dente", "dentista de novo #privado")
    cv.reindexar()
    cv.indexar_vetores()
    con = sqlite3.connect(cv.pasta_indice / "vetores.sqlite")
    assert con.execute("SELECT privado FROM vetores WHERE caminho='entrada/x.md'").fetchone() == (1,)
    con.close()


def test_contexto_para_nuvem_nunca_leva_privada_achada_por_significado(cv):
    _nota(cv, "privado/saude.md", "Saúde", "SEGREDO-DE-SAUDE consulta com o dentista na terça")
    _nota(cv, "entrada/etiqueta.md", "Dente", "dentista na quarta SEGREDO-DA-ETIQUETA #privado")
    cv.reindexar()
    cv.indexar_vetores()
    ctx = cv.contexto_para_nuvem("quando é o dentista?")
    assert "odontológica" in ctx                            # a pública, achada por significado, vai
    assert "SEGREDO" not in ctx and "saude" not in ctx.lower()


def test_contexto_confere_na_nota_se_o_indice_esta_velho(cv):
    cv.indexar_vetores()
    p = cv.raiz / "entrada" / "consulta.md"
    p.write_text(p.read_text(encoding="utf-8") + "\n#privado\n", encoding="utf-8")   # virou privada agora
    assert "odontológica" not in cv.contexto_para_nuvem("quando é o dentista?")


def test_voz_nao_le_titulo_nem_trecho_de_privada_achada_por_significado(cv):
    _nota(cv, "privado/saude.md", "Saúde", "consulta com o dentista na terça")
    (cv.raiz / "entrada" / "consulta.md").unlink()
    cv.reindexar()
    cv.indexar_vetores()
    fala = voz.executar({"tipo": "cofre_buscar", "consulta": "dentista"}, cv)
    assert "Saúde" not in fala and "terça" not in fala and "privada" in fala


def test_voz_usa_a_hibrida(cv):
    cv.indexar_vetores()
    fala = voz.executar({"tipo": "cofre_buscar", "consulta": "dentista"}, cv)
    assert "Consulta odontológica" in fala


# ------------------------------------------------------------- fundo e memória
def test_vetorizar_em_fundo_nao_bloqueia_e_conclui(tmp_path):
    c = cofre.Cofre(tmp_path / "c", semantica=True, embedder=Falso())
    rel = c.escrever("Dentista", "consulta odontológica", pasta="entrada")
    c.indexar_nota(rel)
    c._fio_vetores.join(5)
    assert (c.pasta_indice / "vetores.sqlite").exists()
    assert [a["caminho"] for a in c.buscar_hibrido("dente")] == [rel]


def test_libera_o_modelo_ocioso(cv):
    cv.indexar_vetores()
    assert cv.liberar_modelo_se_ocioso(segundos=3600) is False
    cv._embedder.ultimo_uso = time.monotonic() - 7200
    assert cv.liberar_modelo_se_ocioso(segundos=3600) is True
    assert cv._embedder.liberado == 1


def test_config_cofre_semantica_padrao_falso_e_validada():
    import dervs_config
    assert dervs_config.PADRAO["cofre_semantica"] is False
    assert dervs_config._validar(dict(dervs_config.PADRAO, cofre_semantica="sim"))["cofre_semantica"] is False


# ------------------------------------------------------------- o modelo de verdade
def _modelo_real_pronto():
    return sem.pacote_instalado() and sem.EmbedderFastembed(baixar=False)._em_cache()


@pytest.mark.skipif(not _modelo_real_pronto(), reason="sem fastembed ou sem o modelo em disco (opcional)")
def test_modelo_real_acha_dentista_por_consulta_odontologica(tmp_path):
    c = cofre.Cofre(tmp_path / "c", semantica=True, embedder=sem.EmbedderFastembed(baixar=False))
    _nota(c, "entrada/a.md", "Consulta odontológica", "Marcada para terça às 15h.")
    _nota(c, "entrada/b.md", "Receita", "Salada com legumes e frango grelhado.")
    c.reindexar()
    assert c.semantica_disponivel()
    assert c.indexar_vetores() == 2
    achados = c.buscar_hibrido("dentista")
    assert achados and achados[0]["caminho"] == "entrada/a.md"
