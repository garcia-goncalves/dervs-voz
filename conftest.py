"""Configuração do pytest para o repositório inteiro.

Existe por um motivo só: manter as cópias de trabalho temporárias fora da
coleta de testes, inclusive quando alguém passa o caminho delas na mão.

Quando vários agentes trabalham em paralelo, cada um ganha uma cópia do
repositório em `.claude/worktrees/agent-<id>/`. Essas cópias têm arquivos de
teste com os MESMOS nomes dos daqui, e isso quebra o pytest de duas maneiras
diferentes, dependendo do modo de importação:

  - no modo padrão, dois `test_dervs_safety.py` fazem o pytest abortar a coleta
    inteira com "import file mismatch" — e aí nenhum teste roda, nem os bons;
  - no modo `importlib` (que resolve o de cima, ver `pytest.ini`), o pytest
    tenta virar o caminho em nome de módulo e engasga no ponto de `.claude`:
    "the 'package' argument is required to perform a relative import".

`norecursedirs` no `pytest.ini` já evita a varredura automática, mas NÃO vale
quando o caminho é passado explicitamente na linha de comando — que é
justamente o que as ferramentas de verificação fazem. O gancho abaixo vale nos
dois casos.
"""
import json
import os
import tempfile

# Os testes NÃO podem ler nem gravar a configuração de verdade do dono. Antes
# disto, ligar o microfone pelo botão gravava `escuta_ao_abrir: true` em
# %APPDATA%\dervs e, dali em diante, todo teste que criava a janela abria o
# microfone real — duas threads no mesmo dispositivo derrubavam o Python com
# 0xc0000374 (heap corrompido), em ponto aleatório da suíte. Tem de rodar
# antes de qualquer teste importar `dervs_config`, que fixa o caminho ao importar.
# Só o APPDATA (config e .env): o LOCALAPPDATA guarda os modelos de voz, que
# vários testes usam de verdade.
_APPDATA_REAL = os.environ.get("APPDATA") or os.path.expanduser("~/AppData/Roaming")
_CASA_DE_TESTE = tempfile.mkdtemp(prefix="dervs-teste-")
os.environ["APPDATA"] = os.path.join(_CASA_DE_TESTE, "Roaming")
os.makedirs(os.path.join(os.environ["APPDATA"], "dervs"), exist_ok=True)
# o índice do cofre mora no LOCALAPPDATA real (dervs_cofre.pasta_indice_padrao): os testes
# usam a casa de teste, para não deixar um índice por pasta temporária na máquina do dono
os.environ["DERVS_COFRE_INDICE"] = os.path.join(_CASA_DE_TESTE, "cofre-indice")

# Parte da configuração real (não tem segredo: a chave mora no .env), para o
# teste exercitar o mesmo motor e as mesmas vozes que o dono usa, mas com a
# escuta fechada — o padrão do programa é nascer ouvindo, e teste não pode
# abrir microfone.
try:
    with open(os.path.join(_APPDATA_REAL, "dervs", "config.json"), encoding="utf-8") as _f:
        _conf = json.load(_f)
except Exception:
    _conf = {}
_conf["escuta_ao_abrir"] = False
_conf["modo_escuta"] = "desligado"   # Onda A: é ele que decide abrir o microfone
with open(os.path.join(os.environ["APPDATA"], "dervs", "config.json"), "w", encoding="utf-8") as _f:
    json.dump(_conf, _f)


def _e_rascunho(caminho) -> bool:
    partes = os.path.normpath(str(caminho)).split(os.sep)
    return ".claude" in partes


def pytest_ignore_collect(collection_path, config):
    """Não varrer `.claude/` ao procurar testes."""
    return True if _e_rascunho(collection_path) else None


def pytest_collection_modifyitems(config, items):
    """Descartar o que tiver escapado.

    O gancho de cima NÃO vale para caminho passado na linha de comando — é uma
    exceção documentada do pytest, e é exatamente o caso das ferramentas de
    verificação, que passam o arquivo na mão. Este aqui roda depois da coleta e
    pega tudo, venha de onde vier.
    """
    if not items:
        return
    ficam = [item for item in items if not _e_rascunho(item.path)]
    if len(ficam) != len(items):
        config.hook.pytest_deselected(items=[i for i in items if _e_rascunho(i.path)])
        items[:] = ficam
