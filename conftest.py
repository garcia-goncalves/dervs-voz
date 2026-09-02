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
import os


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
