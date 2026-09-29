"""Da leitura dos temporários para PROPOSTAS de limpeza — nunca para ação.

O que sai daqui vai para `Motor.analisar` (onda C), que confere cada item no
disco, recusa o protegido e monta o relatório. Depois disso só o clique do
dono no painel aprova, e o executor manda para a QUARENTENA (nunca apaga), com
Desfazer. Este módulo não importa o executor nem o motor: não tem como agir.

Decisão sobre `C:\\Windows\\Temp` (e `Windows.old`): FICAM DE FORA. São
caminhos protegidos e a exceção não foi aberta — aparecem no relatório como
informação, com o tamanho, e a limpeza deles é feita pela Limpeza de Disco do
próprio Windows, que pede administrador.
"""
import os

GRUPOS_SO_INFORMATIVOS = ("Temporários do Windows", "Instalação antiga do Windows", "Lixeira")
LIMITE_PADRAO = 20
# Programa, biblioteca e script não entram na sugestão: apagar o que executa é
# decisão que o dono toma olhando o arquivo, não uma "sobra" de temporários.
EXTENSOES_FORA = (".exe", ".dll", ".sys", ".msi", ".msp", ".msix", ".ps1", ".bat", ".cmd", ".vbs",
                  ".js", ".lnk", ".scr", ".com", ".ocx")

# Como a tela chama cada grupo, em palavras de quem não é técnico.
TITULOS = {"Temporários do usuário": "Arquivo temporário", "Miniaturas": "Miniaturas de fotos do Windows"}
O_QUE_E = {
    "Temporários do usuário": "Sobra que um programa criou enquanto trabalhava e esqueceu de apagar.",
    "Miniaturas": ("Cópias pequenas das suas fotos e vídeos que o Windows guarda para abrir as pastas mais "
                   "rápido. Ele refaz sozinho quando precisar."),
}

_POR_QUE = {
    "Temporários do usuário": ("Arquivo temporário com mais de 7 dias, fora de uso agora. Programas "
                               "recriam o que precisam quando abrem."),
    "Miniaturas": "Cache de miniaturas do Explorer com mais de 7 dias; o Windows gera de novo sozinho.",
}


def propostas(ultima: dict, limite: int = LIMITE_PADRAO) -> list:
    coletor = ((ultima or {}).get("coletores") or {}).get("temporarios") or {}
    if not coletor.get("ok"):
        return []
    saida = []
    for c in sorted(coletor.get("candidatos") or [], key=lambda x: -x.get("tamanho_bytes", 0)):
        grupo = c.get("grupo", "")
        if grupo not in _POR_QUE or os.path.splitext(c["caminho"])[1].casefold() in EXTENSOES_FORA:
            continue
        # `explicacao` fica vazia de propósito: o motor a rotula "Explicação do Claude",
        # e este texto é do DERVS. A idade do arquivo vai junto do "por que é seguro".
        saida.append({
            "acao": "quarentena", "alvo": c["caminho"], "risco": "baixo", "grupo": grupo,
            "por_que_seguro": f"{_POR_QUE[grupo]} Este está parado há {c.get('idade_dias', '?')} dias."})
        if len(saida) >= limite:
            break
    return saida


def informativos(ultima: dict) -> list:
    """Grupos que só se mostram (não se propõe apagar), com o tamanho."""
    coletor = ((ultima or {}).get("coletores") or {}).get("temporarios") or {}
    return [{"nome": i["nome"], "tamanho_bytes": i["tamanho_bytes"]}
            for i in coletor.get("itens") or [] if i.get("nome") in GRUPOS_SO_INFORMATIVOS]
