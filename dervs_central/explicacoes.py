"""Explicação leiga por item, em tabela local — não gasta modelo.

O botão "Explicar melhor" do painel manda UM item ao Claude Code; aqui está só
o texto que aparece sem gastar nada.
"""

# (trecho da fonte em minúsculas, id ou None) -> texto
_EVENTOS = (
    (("kernel-power", 41), "O PC desligou sem avisar — geralmente queda de energia, botão de "
                           "desligar segurado ou um travamento total."),
    (("eventlog", 6008), "O Windows registrou que o desligamento anterior foi inesperado."),
    (("bugcheck", 1001), "O Windows mostrou a tela azul e se reiniciou para se proteger de um erro grave."),
    (("whea-logger", None), "O processador ou a memória reportou um erro de hardware. Se repetir, "
                            "vale testar a memória e a temperatura."),
    (("service control manager", 7031), "Um serviço do Windows parou de funcionar sozinho."),
    (("service control manager", 7034), "Um serviço do Windows terminou de forma inesperada."),
    (("application error", 1000), "Um programa fechou por causa de um erro dele mesmo."),
)

_GERAL = {
    "disco_cheio": "Disco quase cheio deixa o computador lento e pode impedir atualizações.",
    "disco_doente": "O disco avisou que está com defeito. O certo é copiar o que importa para outro lugar.",
    "defender_desligado": "Sem essa proteção, um vírus pode agir sem ser barrado.",
    "firewall_desligado": "O firewall bloqueia tentativas de entrar no computador pela rede.",
    "seguranca_pendente": "Atualizações de segurança fecham brechas conhecidas; quanto mais demora, mais exposto.",
    "reinicio_pendente": "Basta reiniciar quando puder; nada se perde se você salvar o trabalho antes.",
    "erro_critico": "Erros críticos repetidos indicam um problema que não passa sozinho.",
    "driver_com_erro": "Um dispositivo (som, rede, vídeo...) pode não funcionar direito até o driver ser reinstalado.",
    "commit_sem_push": "Trabalho que existe só neste computador some se o disco falhar. Mandar para o GitHub é a cópia de segurança.",
}


def explicar_evento(fonte: str, ident) -> str:
    f = (fonte or "").casefold()
    for (trecho, i), texto in _EVENTOS:
        if trecho in f and (i is None or i == ident):
            return texto
    return "Erro registrado pelo Windows sem explicação pronta. Use 'Explicar melhor' para pedir ao Claude."


def explicar(codigo: str) -> str:
    return _GERAL.get(codigo, "")
