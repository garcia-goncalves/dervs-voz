#!/usr/bin/env python3
"""DERVS — caminhos que NUNCA se apagam, nem com aprovação (onda C).

A regra do dono: "Não pode apagar nada sem antes analisar tudo profundamente
e me dizer o que é cada coisa que quer apagar. Sempre com minha aprovação."
O motor de aprovação (`dervs_aprovacao.py`) cuida do "analisar" e do "sempre
com minha aprovação". Este arquivo é o chão por baixo dele: a lista do que
nem uma aprovação libera — o Windows, os programas, a raiz dos perfis, as
chaves (.ssh, .gnupg), os repositórios, a própria configuração do DERVS e as
pastas que o dono declarar (onde moram os dados de paciente).

Como decide, em ordem, e sempre "na dúvida, protegido":
  1. Só aceita caminho absoluto com letra de disco. Relativo (`..\\..`),
     caminho de rede (`\\\\servidor`), fluxo alternativo (`a.txt:x`), coringa,
     byte nulo e nome terminado em ponto ou espaço (o Windows os ignora, então
     `C:\\Windows.` É o `C:\\Windows`) são recusados antes de tudo.
  2. Resolve o caminho REAL (`os.path.realpath`): desfaz `..`, nome curto 8.3,
     maiúsculas, barra trocada e o prefixo `\\\\?\\`.
  3. Qualquer junção ou link simbólico no caminho = protegido. Mesmo apontando
     para lugar inofensivo: o alvo de um atalho pode ser trocado depois da
     análise.
  4. Compara o caminho (o escrito E o real) com a lista, sem diferenciar
     maiúsculas. Quem CONTÉM algo protegido também é protegido — apagar
     `~\\source` apagaria os repositórios.
  5. Qualquer erro no meio do caminho = protegido.

Documentos, Área de Trabalho, Downloads, Imagens, Vídeos, Música e OneDrive:
a pasta em si nunca se apaga; um arquivo solto dentro dela pode (com análise e
clique); em massa (`em_massa=True`), não.

A lista extra do dono mora em `%APPDATA%\\dervs\\caminhos_protegidos.json`,
formato `{"caminhos": ["D:\\\\Consultorio", ...]}`. Se o arquivo existir e
estiver ilegível, TUDO fica protegido até ele ser consertado. Esses caminhos
são lidos só aqui, localmente — nunca vão para serviço de fora.
"""
import ctypes
import functools
import json
import os
import re
import stat
import sys
import uuid

_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_SISTEMA = getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 0x4)

_MODELO_EXTRAS = {
    "LEIA-ME": ("Pastas que o DERVS NUNCA apaga, nem com aprovação. Ponha aqui as pastas "
                "dos programas que guardam dado de paciente (e qualquer outra que queira "
                "blindar), com barra dupla: \"D:\\\\Consultorio\". Salve e pronto: vale "
                "na hora. Se o arquivo ficar com erro de digitação, o DERVS se recusa a "
                "apagar qualquer coisa até ele ser consertado."),
    "caminhos": [],
}

# Nomes que, em QUALQUER ponto do caminho, protegem tudo abaixo.
_COMPONENTES = {
    ".git": "pasta de controle de versão de um projeto (.git)",
    ".claude": "configuração e memória do Claude Code (.claude)",
    ".ssh": "chaves de acesso SSH (.ssh)",
    ".gnupg": "chaves de criptografia (.gnupg)",
    ".aws": "credenciais de nuvem (.aws)",
    "$recycle.bin": "a Lixeira do Windows",
    "system volume information": "pontos de restauração do Windows",
}
_ARQUIVOS_DE_SISTEMA = {"pagefile.sys", "hiberfil.sys", "swapfile.sys"}
_PESSOAIS = ("Documents", "Desktop", "Downloads", "Pictures", "Videos", "Music",
             "Documentos", "Área de Trabalho", "Imagens", "Vídeos", "Músicas")
_CURINGAS = set('*?"<>|')
_CURTO_83 = re.compile(r"^[^~\\]{1,6}~\d+(\.[^.\\]{0,3})?$")


def _env(ambiente, nome, padrao=""):
    fonte = ambiente if ambiente is not None else os.environ
    valor = fonte.get(nome)
    if not valor and ambiente is not None:
        valor = os.environ.get(nome)
    return valor or padrao


def arquivo_extras(ambiente=None) -> str:
    base = _env(ambiente, "APPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(base, "dervs", "caminhos_protegidos.json")


def garantir_arquivo_extras(caminho: str | None = None) -> str:
    """Cria o modelo vazio (com o LEIA-ME dentro) se ainda não existe. Nunca
    sobrescreve o que o dono escreveu."""
    caminho = caminho or arquivo_extras()
    if not os.path.exists(caminho):
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "x", encoding="utf-8", newline="\n") as f:
            json.dump(_MODELO_EXTRAS, f, ensure_ascii=False, indent=2)
    return caminho


def carregar_extras(caminho: str | None = None) -> list:
    """A lista do dono. Arquivo ausente = lista vazia; arquivo ilegível =
    `ValueError` (quem chama trata como 'tudo protegido')."""
    caminho = caminho or arquivo_extras()
    try:
        with open(caminho, encoding="utf-8-sig") as f:
            dados = json.load(f)
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as erro:
        raise ValueError(f"lista de caminhos protegidos ilegível ({type(erro).__name__})") from None
    lista = dados.get("caminhos") if isinstance(dados, dict) else None
    if not isinstance(lista, list) or not all(isinstance(c, str) and c.strip() for c in lista):
        raise ValueError("lista de caminhos protegidos ilegível (esperado {\"caminhos\": [...]})")
    return lista


def _tirar_prefixo(texto: str) -> str | None:
    for prefixo in ("\\\\?\\UNC\\", "\\??\\UNC\\"):
        if texto.upper().startswith(prefixo):
            return None
    for prefixo in ("\\\\?\\", "\\\\.\\", "\\??\\"):
        if texto.startswith(prefixo):
            texto = texto[len(prefixo):]
            break
    if texto.startswith("\\\\"):
        return None
    return texto


def _lexico(caminho) -> str | None:
    """O caminho absoluto escrito, com `..` desfeito mas SEM seguir atalho.
    None = entrada que não se aceita (ver o passo 1 do topo)."""
    if isinstance(caminho, bytes) or not isinstance(caminho, (str, os.PathLike)):
        return None
    texto = os.fspath(caminho)
    if not isinstance(texto, str) or not texto.strip() or "\x00" in texto:
        return None
    texto = _tirar_prefixo(texto.replace("/", "\\"))
    if texto is None or not re.match(r"^[A-Za-z]:\\", texto):
        return None
    if ":" in texto[2:] or _CURINGAS & set(texto):
        return None
    for parte in texto[3:].split("\\"):
        if parte not in ("", ".", "..") and parte != parte.rstrip(". "):
            return None
    return os.path.normpath(texto)


def normalizar(caminho) -> str | None:
    """O caminho REAL (atalhos seguidos, 8.3 expandido, sem `\\\\?\\`), ou None
    se a entrada é inaceitável."""
    lexico = _lexico(caminho)
    if lexico is None:
        return None
    real = _tirar_prefixo(os.path.realpath(lexico))
    if real is None or not re.match(r"^[A-Za-z]:\\", real) or ":" in real[2:]:
        return None
    return real


def _chave(caminho: str) -> str:
    chave = os.path.normcase(caminho).rstrip("\\")
    return chave + "\\" if len(chave) <= 2 else chave


def _dentro(filho: str, pai: str) -> bool:
    """Os dois já em forma de chave."""
    pai = pai.rstrip("\\")
    filho = filho.rstrip("\\")
    return filho == pai or filho.startswith(pai + "\\")


def eh_link(caminho: str) -> bool:
    try:
        st = os.lstat(caminho)
    except FileNotFoundError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & _REPARSE) or stat.S_ISLNK(st.st_mode)


def link_no_caminho(caminho: str) -> bool:
    """Algum pedaço do caminho (do disco até o fim) é junção ou link?"""
    atual = caminho[:3]
    for parte in caminho[3:].split("\\"):
        if not parte:
            continue
        atual = os.path.join(atual, parte)
        if eh_link(atual):
            return True
    return False


def problema_dentro(pasta: str, limite: int = 20000) -> str:
    """Motivo para NÃO mexer numa pasta por causa do que há DENTRO dela:
    junção ou link em qualquer nível, pasta protegida lá no fundo (um `.git`,
    um `.ssh`), pasta grande demais para olhar inteira ou pedaço ilegível.
    "" = nada encontrado. Na dúvida, devolve motivo."""
    vistos = 0
    pilha = [pasta]
    while pilha:
        atual = pilha.pop()
        try:
            with os.scandir(atual) as entradas:
                for e in entradas:
                    vistos += 1
                    if vistos > limite:
                        return f"pasta grande demais para analisar item a item (mais de {limite} itens)"
                    if eh_link(e.path):
                        return f"tem uma junção ou atalho simbólico dentro ({e.name})"
                    if e.name.casefold() in _COMPONENTES:
                        return f"tem dentro {_COMPONENTES[e.name.casefold()]}"
                    if eh_de_sistema(e.path):
                        return f"tem dentro um item marcado como de sistema pelo Windows ({e.name})"
                    if e.is_dir(follow_symlinks=False):
                        pilha.append(e.path)
        except OSError:
            return "tem uma parte que não deu para ler — não dá para saber o que tem lá"
    return ""


def _pastas_padrao(ambiente) -> list[tuple[str, str]]:
    """(caminho, motivo) de cada subárvore protegida por padrão."""
    perfil = _env(ambiente, "USERPROFILE") or os.path.expanduser("~")
    appdata = _env(ambiente, "APPDATA") or os.path.join(perfil, "AppData", "Roaming")
    local = _env(ambiente, "LOCALAPPDATA") or os.path.join(perfil, "AppData", "Local")
    windows = _env(ambiente, "SystemRoot", r"C:\Windows")
    sistema = "pasta do sistema Windows"
    programas = "pasta de programas instalados"
    dados_sistema = "dados de programas do sistema (ProgramData)"
    dervs_conf = "configuração e chaves do próprio DERVS"
    dervs_local = "registro e quarentena do próprio DERVS"
    cofre = "chaves e senhas guardadas pelo Windows"
    navegador = "perfil de navegador (senhas, cookies, histórico)"
    roamings = {appdata, os.path.join(perfil, "AppData", "Roaming")}
    locais = {local, os.path.join(perfil, "AppData", "Local")}
    sensiveis = []
    for r in roamings:
        sensiveis += [(os.path.join(r, "Microsoft", "Protect"), cofre),
                      (os.path.join(r, "Microsoft", "Credentials"), cofre),
                      (os.path.join(r, "Microsoft", "Crypto"), cofre),
                      (os.path.join(r, "Microsoft", "SystemCertificates"), cofre),
                      (os.path.join(r, "Mozilla", "Firefox", "Profiles"), navegador),
                      (os.path.join(r, "Opera Software"), navegador)]
    for l in locais:
        sensiveis += [(os.path.join(l, "Microsoft", "Credentials"), cofre),
                      (os.path.join(l, "Microsoft", "Vault"), cofre),
                      (os.path.join(l, "Google", "Chrome", "User Data"), navegador),
                      (os.path.join(l, "Microsoft", "Edge", "User Data"), navegador),
                      (os.path.join(l, "BraveSoftware", "Brave-Browser", "User Data"), navegador),
                      (os.path.join(l, "Mozilla", "Firefox", "Profiles"), navegador)]
    return sensiveis + [
        (r"C:\Recovery", "partição de recuperação do Windows"),
        (windows, sistema), (r"C:\Windows", sistema),
        (_env(ambiente, "ProgramFiles", r"C:\Program Files"), programas),
        (_env(ambiente, "ProgramFiles(x86)", r"C:\Program Files (x86)"), programas),
        (_env(ambiente, "ProgramW6432", r"C:\Program Files"), programas),
        (r"C:\Program Files", programas), (r"C:\Program Files (x86)", programas),
        (_env(ambiente, "ProgramData", r"C:\ProgramData"), dados_sistema),
        (r"C:\ProgramData", dados_sistema),
        (os.path.join(perfil, "source", "repos"), "pasta dos projetos (repositórios)"),
        (os.path.join(appdata, "dervs"), dervs_conf),
        (os.path.join(perfil, "AppData", "Roaming", "dervs"), dervs_conf),
        (os.path.join(local, "dervs"), dervs_local),
        (os.path.join(perfil, "AppData", "Local", "dervs"), dervs_local),
    ]


# Pastas conhecidas do Windows (Área de Trabalho, Documentos, Downloads,
# Imagens, Vídeos, Músicas). Podem ter sido redirecionadas para o D: ou para
# o OneDrive — então quem diz onde estão é o próprio Windows.
_PASTAS_CONHECIDAS = (
    "B4BFCC3A-DB2C-424C-B029-7FE99A87C641", "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "374DE290-123F-4565-9164-39C4925E467B", "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "18989B1D-99B5-455B-841C-AB7C74E4DDFC", "4BD8D571-6D19-48D3-BE97-422220080E43",
)


@functools.lru_cache(maxsize=1)
def pastas_conhecidas() -> tuple:
    if sys.platform != "win32":
        return ()
    saida = []
    for texto in _PASTAS_CONHECIDAS:
        guid = ctypes.create_string_buffer(uuid.UUID(texto).bytes_le, 16)
        resultado = ctypes.c_wchar_p()
        try:
            erro = ctypes.windll.shell32.SHGetKnownFolderPath(guid, 0, None, ctypes.byref(resultado))
        except OSError:
            continue
        if erro == 0 and resultado.value:
            saida.append(resultado.value)
        if resultado:
            ctypes.windll.ole32.CoTaskMemFree(resultado)
    return tuple(saida)


def eh_de_sistema(caminho: str) -> bool:
    try:
        return bool(getattr(os.lstat(caminho), "st_file_attributes", 0) & _SISTEMA)
    except FileNotFoundError:
        return False


def _pessoais(perfil: str, reais: bool = True) -> list[str]:
    saida = [os.path.join(perfil, p) for p in _PESSOAIS]
    if reais:
        saida += list(pastas_conhecidas())
    saida.append(os.path.join(perfil, "OneDrive"))
    try:
        for e in os.scandir(perfil):
            if e.name.casefold().startswith("onedrive"):
                saida.append(e.path)
                saida += [os.path.join(e.path, p) for p in _PESSOAIS]
    except OSError:
        pass
    return saida


def _perfil(ambiente) -> str:
    perfil = _env(ambiente, "USERPROFILE") or os.path.expanduser("~")
    return normalizar(perfil) or perfil


def dentro_de_pasta_pessoal(caminho_real: str, ambiente=None) -> bool:
    chave = _chave(caminho_real)
    return any(_dentro(chave, _chave(p)) for p in _pessoais(_perfil(ambiente), ambiente is None))


def _dentro_de_repositorio(real: str) -> bool:
    atual = os.path.dirname(real)
    while True:
        if os.path.lexists(os.path.join(atual, ".git")):
            return True
        pai = os.path.dirname(atual)
        if pai == atual:
            return False
        atual = pai


def _avaliar(chave: str, subarvores, perfil: str, pessoais, em_massa: bool) -> str:
    partes = chave.rstrip("\\").split("\\")
    if len(partes) <= 1:
        return "é a raiz de um disco"
    if len(partes) == 2:
        return "fica direto na raiz do disco (lugar de arquivo do sistema)"
    for parte in partes[1:]:
        if parte in _COMPONENTES:
            return _COMPONENTES[parte]
    if partes[-1] in _ARQUIVOS_DE_SISTEMA:
        return "arquivo de memória do Windows"
    for pasta, motivo in subarvores:
        if _dentro(chave, pasta):
            return motivo
        if _dentro(pasta, chave):
            return f"contém uma pasta protegida ({motivo})"
    usuarios = perfil.rsplit("\\", 1)[0]
    if _dentro(perfil, chave):
        return "é o seu perfil de usuário inteiro, ou uma pasta que o contém"
    if _dentro(chave, usuarios):
        if not _dentro(chave, perfil):
            return "pasta de outro usuário deste computador"
    for pasta in pessoais:
        if _dentro(pasta, chave):
            return "pasta pessoal inteira (Documentos, Área de Trabalho, Downloads...)"
        if em_massa and _dentro(chave, pasta):
            return "exclusão em massa dentro de pasta pessoal — só item a item"
    return ""


def esta_protegido(caminho, *, em_massa: bool = False, extras=None,
                   ambiente=None) -> tuple[bool, str]:
    """(True, motivo em português) se o DERVS não pode tocar neste caminho;
    (False, "") se pode — ainda sujeito à análise e ao clique do dono.

    `extras`: lista de caminhos a mais; None = ler o arquivo do dono.
    `em_massa`: o pedido apaga muita coisa de uma vez (pasta inteira ou lote).
    """
    try:
        lexico = _lexico(caminho)
        if lexico is None:
            return True, ("caminho inválido ou disfarçado (relativo, de rede, com coringa "
                          "ou com ponto/espaço no fim)")
        real = normalizar(lexico)
        if real is None:
            return True, "não foi possível resolver o caminho real"
        for pedaco in os.path.normcase(real).split("\\"):
            if _CURTO_83.match(pedaco):
                return True, "nome curto do Windows (8.3) que não foi possível expandir"
        if link_no_caminho(lexico) or link_no_caminho(real):
            return True, "passa por uma junção ou atalho simbólico — o destino pode ser trocado"
        if eh_de_sistema(real):
            return True, "item marcado como de sistema pelo Windows"
        if extras is None:
            try:
                extras = carregar_extras(arquivo_extras(ambiente))
            except ValueError as erro:
                return True, f"{erro} — nada se apaga até o arquivo ser consertado"
        subarvores = [(_chave(p), m) for p, m in _pastas_padrao(ambiente)]
        for extra in extras:
            resolvido = normalizar(extra) or _lexico(extra)
            if resolvido is None:
                return True, "um caminho da lista de protegidos é inválido — nada se apaga até consertar"
            subarvores.append((_chave(resolvido), "pasta que você marcou como protegida"))
        perfil = _perfil(ambiente)
        pessoais = [_chave(p) for p in _pessoais(perfil, ambiente is None)]
        for alvo in (lexico, real):
            motivo = _avaliar(_chave(alvo), subarvores, _chave(perfil), pessoais, em_massa)
            if motivo:
                return True, motivo
        if _dentro_de_repositorio(real):
            return True, "fica dentro de um repositório de código (projeto com .git)"
        return False, ""
    except Exception as erro:  # na dúvida, protegido
        return True, f"erro ao analisar o caminho ({type(erro).__name__}) — por segurança, não se toca"
