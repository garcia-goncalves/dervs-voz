#!/usr/bin/env python3
"""Testes da lista de caminhos protegidos (onda C da central do PC).

A regra do dono: "Não pode apagar nada sem antes analisar tudo profundamente".
Esta lista é o chão abaixo do qual nem uma aprovação desce: o que está aqui
NUNCA se apaga, nem com clique. A parte que mais importa é a de propriedade no
fim do arquivo — nenhuma grafia torta do mesmo caminho (barra trocada,
maiúsculas, `\\\\?\\`, nome curto 8.3, `..`, ponto ou espaço no fim, atalho
simbólico) escapa da lista.

Só lê o disco (e cria atalhos dentro de `tmp_path`). Nada aqui apaga.

Rodar: python -m pytest test_dervs_caminhos_protegidos.py -q
"""
import json
import os
import sys

import pytest

import dervs_caminhos_protegidos as cp

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="regras de caminho do Windows")

WINDIR = os.environ.get("SystemRoot", r"C:\Windows")
HOME = os.path.expanduser("~")


def _protegido(caminho, **kw):
    kw.setdefault("extras", [])
    return cp.esta_protegido(caminho, **kw)


# ------------------------------------------------------------ os padrões

@pytest.mark.parametrize("caminho", [
    WINDIR,
    os.path.join(WINDIR, "System32", "drivers", "etc", "hosts"),
    r"C:\Program Files",
    r"C:\Program Files\Common Files",
    r"C:\Program Files (x86)",
    r"C:\ProgramData",
    r"C:\ProgramData\Microsoft\Windows",
    r"C:\pagefile.sys",
    r"C:\hiberfil.sys",
    r"C:\System Volume Information",
    r"C:\$Recycle.Bin",
    "C:\\",
    r"C:\qualquer-coisa-na-raiz",
    r"C:\Users",
    HOME,
    os.path.join(os.path.dirname(HOME), "OutroUsuario", "Documents", "x.txt"),
    os.path.join(os.path.dirname(HOME), "Public", "x.txt"),
    os.path.join(HOME, ".ssh", "id_ed25519"),
    os.path.join(HOME, ".gnupg"),
    os.path.join(HOME, ".claude", "settings.json"),
    os.path.join(HOME, "algum", "projeto", ".git", "config"),
    os.path.join(HOME, "source", "repos"),
    os.path.join(HOME, "source", "repos", "dervs-voz", "dervs.py"),
    os.path.join(HOME, "AppData", "Roaming", "dervs", ".env"),
    os.path.join(os.environ["APPDATA"], "dervs", "config.json"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "dervs", "acoes.jsonl"),
    os.path.join(HOME, "Documents"),
    os.path.join(HOME, "Desktop"),
    os.path.join(HOME, "Downloads"),
    os.path.join(HOME, "OneDrive"),
])
def test_padroes_sao_protegidos(caminho):
    protegido, motivo = _protegido(caminho)
    assert protegido, caminho
    assert motivo  # sempre diz o porquê, em português


@pytest.mark.parametrize("caminho", [
    os.path.join(HOME, "AppData", "Roaming", "Microsoft", "Protect", "S-1-5-21", "chave"),
    os.path.join(HOME, "AppData", "Roaming", "Microsoft", "Credentials", "x"),
    os.path.join(HOME, "AppData", "Local", "Microsoft", "Credentials", "x"),
    os.path.join(HOME, "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Cookies"),
    os.path.join(HOME, "AppData", "Local", "Microsoft", "Edge", "User Data", "Default"),
    os.path.join(HOME, "AppData", "Local", "BraveSoftware", "Brave-Browser", "User Data"),
    os.path.join(HOME, "AppData", "Roaming", "Mozilla", "Firefox", "Profiles", "abc.default"),
    r"C:\Recovery\WindowsRE",
])
def test_cofres_de_senha_e_perfis_de_navegador_sao_protegidos(caminho):
    """Revisão de 29/09: as chaves do Windows (DPAPI), as credenciais e os
    perfis de navegador (senhas, cookies) ficavam de fora."""
    protegido, motivo = _protegido(caminho)
    assert protegido and motivo


def test_item_com_atributo_de_sistema_e_protegido(tmp_path):
    import ctypes
    alvo = tmp_path / "desktop.ini"
    alvo.write_text("x")
    assert not _protegido(str(alvo))[0]
    ctypes.windll.kernel32.SetFileAttributesW(str(alvo), 0x4)  # FILE_ATTRIBUTE_SYSTEM
    try:
        protegido, motivo = _protegido(str(alvo))
        assert protegido and "sistema" in motivo
    finally:
        ctypes.windll.kernel32.SetFileAttributesW(str(alvo), 0x80)


def test_pasta_com_item_de_sistema_dentro_e_recusada(tmp_path):
    import ctypes
    (tmp_path / "p").mkdir()
    alvo = tmp_path / "p" / "desktop.ini"
    alvo.write_text("x")
    ctypes.windll.kernel32.SetFileAttributesW(str(alvo), 0x4)
    try:
        assert "sistema" in cp.problema_dentro(str(tmp_path / "p"))
    finally:
        ctypes.windll.kernel32.SetFileAttributesW(str(alvo), 0x80)


def test_pastas_pessoais_de_verdade_vem_do_windows():
    """Documentos pode ter sido redirecionado (para D:, para o OneDrive): a
    pasta que o Windows diz que é a de Documentos é a que vale."""
    reais = cp.pastas_conhecidas()
    assert reais, "o Windows não informou nenhuma pasta conhecida"
    for pasta in reais:
        assert _protegido(pasta)[0], pasta


def test_pasta_que_contem_protegido_tambem_e_protegida():
    """Apagar `~\\source` apagaria os repositórios; apagar `~\\AppData` levaria
    a config do DERVS junto. Ancestral de protegido é protegido."""
    assert _protegido(os.path.join(HOME, "source"))[0]
    assert _protegido(os.path.join(HOME, "AppData"))[0]
    assert _protegido(os.path.join(HOME, "AppData", "Local"))[0]


def test_item_individual_em_pasta_pessoal_passa_mas_nao_em_massa():
    alvo = os.path.join(HOME, "Downloads", "instalador-velho.exe")
    assert _protegido(alvo) == (False, "")
    protegido, motivo = _protegido(alvo, em_massa=True)
    assert protegido and "massa" in motivo


def test_arquivo_comum_no_temp_nao_e_protegido(tmp_path):
    alvo = tmp_path / "sobra.tmp"
    alvo.write_text("x")
    assert _protegido(str(alvo)) == (False, "")


def test_dentro_de_repositorio_git_e_protegido(tmp_path):
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    (tmp_path / "repo" / "src").mkdir()
    protegido, motivo = _protegido(str(tmp_path / "repo" / "src" / "a.py"))
    assert protegido and "reposit" in motivo


# ------------------------------------------------------------ lista extra do dono

def test_lista_extra_do_arquivo_protege(tmp_path):
    consultorio = tmp_path / "Consultorio"
    consultorio.mkdir()
    arquivo = tmp_path / "caminhos_protegidos.json"
    arquivo.write_text(json.dumps({"caminhos": [str(consultorio)]}), encoding="utf-8")
    extras = cp.carregar_extras(str(arquivo))
    assert _protegido(str(consultorio / "paciente.pdf"), extras=extras)[0]
    assert _protegido(str(tmp_path), extras=extras)[0]  # ancestral
    assert not _protegido(str(tmp_path / "outra.txt"), extras=extras)[0]


def test_lista_extra_ilegivel_protege_tudo(tmp_path, monkeypatch):
    """Fail-closed: se o dono estragou o arquivo, o DERVS não sabe onde estão os
    dados de paciente — então não apaga nada."""
    arquivo = tmp_path / "caminhos_protegidos.json"
    arquivo.write_text("{ isto não é json", encoding="utf-8")
    alvo = tmp_path / "sobra.tmp"
    alvo.write_text("x")
    monkeypatch.setattr(cp, "arquivo_extras", lambda ambiente=None: str(arquivo))
    protegido, motivo = cp.esta_protegido(str(alvo))
    assert protegido and "ilegível" in motivo


def test_lista_extra_ausente_nao_protege_nada_a_mais(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "arquivo_extras", lambda ambiente=None: str(tmp_path / "nao-existe.json"))
    alvo = tmp_path / "sobra.tmp"
    alvo.write_text("x")
    assert cp.esta_protegido(str(alvo)) == (False, "")


def test_garantir_arquivo_extras_cria_modelo_vazio_e_valido(tmp_path):
    arquivo = tmp_path / "dervs" / "caminhos_protegidos.json"
    cp.garantir_arquivo_extras(str(arquivo))
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    assert dados["caminhos"] == []
    assert "paciente" in dados["LEIA-ME"]
    arquivo.write_text(json.dumps({"caminhos": ["D:\\X"]}), encoding="utf-8")
    cp.garantir_arquivo_extras(str(arquivo))  # nunca sobrescreve o do dono
    assert json.loads(arquivo.read_text(encoding="utf-8"))["caminhos"] == ["D:\\X"]


# ------------------------------------------------------------ atalhos e junções

def test_juncao_para_pasta_protegida_e_recusada(tmp_path):
    import _winapi
    juncao = tmp_path / "parece-inofensivo"
    _winapi.CreateJunction(WINDIR, str(juncao))
    assert _protegido(str(juncao / "System32" / "x.dll"))[0]
    assert _protegido(str(juncao))[0]


def test_juncao_para_pasta_comum_tambem_e_recusada(tmp_path):
    """Mesmo apontando para lugar inofensivo: o alvo pode ser trocado depois da
    análise. Atalho no caminho = recusa."""
    import _winapi
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "a.txt").write_text("x")
    _winapi.CreateJunction(str(tmp_path / "real"), str(tmp_path / "j"))
    protegido, motivo = _protegido(str(tmp_path / "j" / "a.txt"))
    assert protegido and ("junção" in motivo or "atalho" in motivo)


def test_link_simbolico_para_pasta_protegida_e_recusado(tmp_path):
    link = tmp_path / "link"
    try:
        os.symlink(WINDIR, str(link), target_is_directory=True)
    except OSError:
        pytest.skip("este Windows não deixa criar link simbólico sem administrador")
    assert _protegido(str(link / "System32"))[0]
    assert _protegido(str(link))[0]


def test_link_simbolico_de_arquivo_e_recusado(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    try:
        os.symlink(str(tmp_path / "a.txt"), str(tmp_path / "b.txt"))
    except OSError:
        pytest.skip("este Windows não deixa criar link simbólico sem administrador")
    assert _protegido(str(tmp_path / "b.txt"))[0]


def test_problema_dentro_acha_juncao_dentro_da_pasta(tmp_path):
    import _winapi
    (tmp_path / "pasta" / "sub").mkdir(parents=True)
    assert cp.problema_dentro(str(tmp_path / "pasta")) == ""
    _winapi.CreateJunction(WINDIR, str(tmp_path / "pasta" / "sub" / "j"))
    assert "junção" in cp.problema_dentro(str(tmp_path / "pasta"))


def test_problema_dentro_acha_pasta_protegida_la_no_fundo(tmp_path):
    (tmp_path / "pasta" / "a" / "projeto" / ".git").mkdir(parents=True)
    assert ".git" in cp.problema_dentro(str(tmp_path / "pasta"))


def test_problema_dentro_recusa_pasta_grande_demais(tmp_path):
    (tmp_path / "pasta").mkdir()
    for n in range(5):
        (tmp_path / "pasta" / f"{n}.txt").write_text("x")
    assert cp.problema_dentro(str(tmp_path / "pasta"), limite=3)


# ------------------------------------------------------------ entradas hostis

HOSTIS = [
    r"..\..",
    r"..\..\Windows",
    "Windows\\System32",
    "C:Windows",
    r"\\?\C:\Windows",
    r"\\?\c:\windows\system32\config\SAM",
    r"\\.\C:\Windows",
    r"\??\C:\Windows",
    r"\\?\UNC\servidor\share\x",
    r"\\servidor\share\x",
    "C:/WINDOWS/system32",
    "c:/windows/SYSTEM32/",
    "C:\\\\Windows\\\\\\System32",
    r"C:\PROGRA~1",
    r"C:\PROGRA~1\Common Files",
    r"C:\PROGRA~2",
    r"C:\Windows.",
    r"C:\Windows. ",
    r"C:\Windows \System32",
    r"C:\Windows.\System32",
    r"C:\Program Files.",
    r"C:\Program Files \x",
    r"C:\Windows\.\System32",
    r"C:\Windows\x\..\System32",
    r"C:\Users\x\..\..\Windows",
    r"C:\Windows\win.ini:stream",
    r"C:\Windows\win.ini::$DATA",
    r"C:\Windows\*",
    r"C:\Windows\System32\?",
    "C:\\Windows\x00.txt",
    "",
    "   ",
    None,
    123,
    b"C:\\Windows",
]


@pytest.mark.parametrize("caminho", HOSTIS)
def test_entrada_hostil_nunca_passa(caminho):
    protegido, motivo = cp.esta_protegido(caminho, extras=[])
    assert protegido, repr(caminho)
    assert motivo


def _variantes(base):
    """Grafias diferentes para o MESMO lugar."""
    corpo = base[3:]
    letra = base[0]
    saidas = set()
    for drive in (letra.upper(), letra.lower()):
        for sep in ("\\", "/"):
            for caixa in (str.lower, str.upper, lambda s: s):
                c = drive + ":" + sep + caixa(corpo).replace("\\", sep)
                saidas.add(c)
                saidas.add(c + sep)
                saidas.add("\\\\?\\" + c.replace("/", "\\"))
                saidas.add(c + sep + "." + sep + "x")
                saidas.add(c + sep + "sub" + sep + ".." + sep + "x")
                saidas.add(c + "." + sep + "x")
                saidas.add(c + " " + sep + "x")
    return sorted(saidas)


@pytest.mark.parametrize("base", [
    WINDIR,
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    r"C:\ProgramData\Microsoft",
    os.path.join(HOME, ".ssh"),
    os.path.join(HOME, "source", "repos"),
    os.path.join(os.environ["APPDATA"], "dervs"),
])
def test_propriedade_nenhuma_grafia_do_protegido_escapa(base):
    escaparam = [v for v in _variantes(base) if not cp.esta_protegido(v, extras=[])[0]]
    assert escaparam == []


def test_nome_curto_83_real_de_pasta_comum_resolve(tmp_path):
    """Nome 8.3 de pasta legítima resolve para o nome longo e é comparado por
    ele — o 8.3 não serve de disfarce nem de bloqueio indevido."""
    import ctypes
    longo = tmp_path / "Pasta Com Nome Bem Comprido"
    longo.mkdir()
    buf = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetShortPathNameW(str(longo), buf, 1024)
    curto = buf.value
    if not curto or "~" not in curto:
        pytest.skip("nomes 8.3 desligados neste disco")
    assert cp.normalizar(curto) == cp.normalizar(str(longo))


def test_normalizar_devolve_nome_real_e_nunca_prefixo():
    real = os.path.realpath(WINDIR)
    assert cp.normalizar("c:/windows/SYSTEM32") == os.path.join(real, "System32")
    assert cp.normalizar(r"\\?\C:\Windows") == real
    assert cp.normalizar(r"..\x") is None
    assert cp.normalizar(r"\\srv\share") is None


def test_erro_inesperado_protege(monkeypatch):
    """Qualquer exceção no meio da análise vira 'protegido' — nunca 'livre'."""
    def explode(*a, **k):
        raise RuntimeError("pane")
    monkeypatch.setattr(cp.os.path, "realpath", explode)
    protegido, motivo = cp.esta_protegido(r"C:\Users\x\a.txt", extras=[])
    assert protegido
