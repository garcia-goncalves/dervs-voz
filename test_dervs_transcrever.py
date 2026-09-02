#!/usr/bin/env python3
"""Testes da transcrição de arquivo de áudio.

Nenhum teste aqui chama a API nem o ffmpeg — o que é testado é a decisão: o
arquivo cabe? onde cortar? como emendar sem perder nem repetir palavra?

Rodar: python -m pytest test_dervs_transcrever.py -q
"""
import pytest
import dervs_transcrever as tr


# ---- cabe no envio? ----
def test_arquivo_pequeno_vai_inteiro():
    assert not tr.precisa_encolher(5 * 1024 * 1024)


def test_arquivo_grande_precisa_encolher():
    assert tr.precisa_encolher(40 * 1024 * 1024)


def test_o_limite_tem_margem_para_o_envelope():
    """A API recusa acima de 25 MB, e o envio carrega cabeçalhos junto. Mandar
    24,9 MB de áudio estoura o pedido inteiro por causa do envelope."""
    assert tr.LIMITE_BYTES < 25 * 1024 * 1024


# ---- onde cortar ----
def test_audio_curto_nao_e_cortado():
    assert tr.planejar_pedacos(300.0) == [(0.0, 300.0)]


def test_audio_exatamente_do_tamanho_do_pedaco_nao_e_cortado():
    assert len(tr.planejar_pedacos(float(tr.PEDACO_SEG))) == 1


def test_audio_longo_vira_varios_pedacos():
    partes = tr.planejar_pedacos(3600.0)   # 1 hora
    assert len(partes) > 1


def test_nenhum_pedaco_passa_do_fim_do_audio():
    """Pedir ao ffmpeg um trecho além do fim devolve arquivo vazio, e a API
    recusa arquivo vazio — a transcrição inteira morreria no último pedaço."""
    dur = 3725.0
    for inicio, dura in tr.planejar_pedacos(dur):
        assert inicio + dura <= dur + 0.001, f"pedaço em {inicio} passa do fim"


def test_os_pedacos_cobrem_o_audio_inteiro_sem_buraco():
    """Buraco entre pedaços = trecho da reunião que some do texto, calado."""
    dur = 3725.0
    partes = tr.planejar_pedacos(dur)
    assert partes[0][0] == 0.0
    for (i1, d1), (i2, _) in zip(partes, partes[1:]):
        assert i2 <= i1 + d1, "há um buraco entre dois pedaços"
    fim, dura = partes[-1]
    assert abs((fim + dura) - dur) < 0.001, "o último pedaço não chega ao fim"


def test_os_pedacos_se_sobrepoem():
    """Sem sobreposição, a palavra dita bem na hora do corte se perde."""
    partes = tr.planejar_pedacos(3600.0)
    (i1, d1), (i2, _) = partes[0], partes[1]
    assert i2 < i1 + d1, "os pedaços não se sobrepõem"
    assert (i1 + d1) - i2 == pytest.approx(tr.SOBREPOR_SEG)


# ---- juntar os pedaços ----
def test_emenda_descarta_a_repeticao_da_sobreposicao():
    a = "o cliente pediu o relatório até sexta e disse que precisa do gráfico novo"
    b = "que precisa do gráfico novo com os números de agosto separados por região"
    assert tr.emendar(a, b) == (
        "o cliente pediu o relatório até sexta e disse que precisa do gráfico novo "
        "com os números de agosto separados por região")


def test_emenda_sem_repeticao_junta_os_dois_inteiros():
    """Quando o modelo transcreveu diferente dos dois lados, é melhor repetir do
    que engolir uma frase."""
    a = "primeira parte da reunião sobre o orçamento"
    b = "assunto completamente diferente agora falando de contratação"
    assert tr.emendar(a, b) == a + " " + b


def test_emenda_com_trecho_vazio():
    assert tr.emendar("", "só o segundo") == "só o segundo"
    assert tr.emendar("só o primeiro", "") == "só o primeiro"
    assert tr.emendar("", "") == ""


def test_emenda_nao_corta_por_coincidencia_curta():
    """Duas ou três palavras iguais acontecem por acaso em português ('que a
    gente'). Cortar por causa disso comeria texto de verdade."""
    a = "o prazo termina amanhã e a gente"
    b = "a gente ainda não decidiu quem vai apresentar"
    assert "ainda não decidiu quem vai apresentar" in tr.emendar(a, b)
    assert tr.emendar(a, b).startswith("o prazo termina amanhã")


def test_emenda_so_corta_repeticao_de_fim_com_comeco():
    """Palavra repetida no MEIO dos dois trechos não é sobreposição — é só o
    assunto voltando. Cortar ali perderia o miolo."""
    a = "falamos do contrato e depois mudamos de assunto para as férias"
    b = "voltando ao contrato o prazo de assinatura é dia dez"
    junto = tr.emendar(a, b)
    assert "para as férias" in junto
    assert "o prazo de assinatura é dia dez" in junto


# ---- formatos ----
def test_os_formatos_que_o_dono_usa_de_verdade_sao_aceitos():
    """WhatsApp manda .ogg, iPhone manda .m4a, gravador do Windows manda .m4a."""
    for ext in (".mp3", ".m4a", ".ogg", ".wav", ".mp4"):
        assert ext in tr.FORMATOS


# ---- emenda: casos reais colhidos transcrevendo áudio de verdade ----
# Os três abaixo saíram de uma reunião sintetizada e cortada em pedaços de 12 s.
# Com a emenda ingênua, o texto final tinha 165 palavras onde o original tinha
# 100 — cada emenda repetia o trecho sobreposto inteiro.

def test_emenda_ignora_pontuacao_na_juncao():
    """O modelo fecha a frase num pedaço e não no outro: 'equipe.' vs 'equipe'.
    Comparando com o ponto colado, a última palavra nunca casa e nada é cortado."""
    a = ("O primeiro assunto é o orçamento do trimestre, que fechou 10% acima do "
         "previsto. A causa principal foi o gasto com deslocamento da equipe.")
    b = ("que fechou 10% acima do previsto. A causa principal foi o gasto com "
         "deslocamento da equipe de campo. O segundo assunto é o contrato.")
    junto = tr.emendar(a, b)
    assert junto.count("A causa principal") == 1, f"repetiu: {junto}"
    assert junto.endswith("O segundo assunto é o contrato.")


def test_emenda_ignora_maiuscula_na_juncao():
    """Começo de pedaço vem com maiúscula ('Os números'), meio de frase não."""
    a = ("Marina ficou de trazer os números da concorrência até sexta-feira. "
         "Por último, a contratação do analista de dados continua.")
    b = ("Os números da concorrência até sexta-feira. Por último, a contratação "
         "do analista de dados continua parada esperando aprovação.")
    junto = tr.emendar(a, b)
    assert junto.count("Por último") == 1, f"repetiu: {junto}"
    assert junto.endswith("parada esperando aprovação.")


def test_emenda_aguenta_numero_escrito_diferente():
    """O mesmo trecho vira '12 meses' num pedaço e 'doze meses' no outro. Exigir
    igualdade palavra a palavra desiste da emenda inteira por causa de uma."""
    a = ("Precisamos decidir se renovamos por 12 meses ou se abrimos "
         "concorrência. Marina ficou de trazer os")
    b = ("Precisamos decidir se renovamos por doze meses ou se abrimos "
         "concorrência. Marina ficou de trazer os números da concorrência.")
    junto = tr.emendar(a, b)
    assert junto.count("Precisamos decidir") == 1, f"repetiu: {junto}"
    assert junto.endswith("números da concorrência.")


def test_emenda_tira_o_ponto_que_sobra_no_meio_da_frase():
    """O pedaço acaba no meio da frase e o modelo fecha com ponto: '...da
    equipe.' + 'de campo.' vira 'da equipe. de campo.' — ponto no meio da frase,
    seguido de minúscula. Feio de ler e atrapalha quem for resumir depois."""
    a = "A causa principal foi o gasto com deslocamento da equipe."
    b = "de campo. O segundo assunto é o contrato."
    assert tr.emendar(a, b) == (
        "A causa principal foi o gasto com deslocamento da equipe de campo. "
        "O segundo assunto é o contrato.")


def test_emenda_preserva_o_ponto_quando_a_frase_acabou_mesmo():
    """Se o próximo começa com maiúscula, o ponto está certo — não mexer."""
    a = "A reunião terminou."
    b = "Depois disso ninguém falou mais nada."
    assert tr.emendar(a, b) == "A reunião terminou. Depois disso ninguém falou mais nada."


def test_emenda_nao_olha_alem_do_que_a_sobreposicao_cabe():
    """O tamanho da janela do lado do próximo É a proteção: 6 s de fala cabem em
    ~20 palavras, então olhar 60 é convite para casar num trecho que não é a
    sobreposição."""
    assert tr.JANELA_PROXIMO <= 30


def test_emenda_nao_come_texto_quando_o_bordao_se_repete():
    """Achado na revisão de 02/09, com reprodução: se um bordão do dono aparece
    no fim de um pedaço E de novo lá adiante no próximo, o maior bloco comum
    casa na SEGUNDA aparição, e tudo que vem antes dela some sem aviso.

    Perder texto calado é o pior resultado possível: quem lê nota uma repetição,
    mas não tem como notar o que não está lá."""
    bordao = "entao a gente precisa ver isso com calma"
    # a sobreposição é transcrita DIFERENTE dos dois lados (o modelo faz isso),
    # então o maior bloco comum não é ela — é o bordão repetido lá adiante.
    a = f"o primeiro ponto e o orcamento do trimestre e {bordao}"
    b = ("primeiro ponto e o orcamento do trimestre. O proximo ponto e o "
         "contrato de manutencao que vence em marco e ninguem olhou ainda, "
         f"{bordao} antes de assinar qualquer coisa")
    junto = tr.emendar(a, b)
    assert "contrato de manutencao que vence em marco" in junto, (
        f"comeu o miolo da reuniao: {junto}")


def test_emenda_preserva_todo_o_conteudo_novo():
    """Rede geral: nenhuma palavra que só existe no segundo trecho pode sumir."""
    a = "falamos do orçamento e ficou decidido que sobe dez por cento"
    b = ("que sobe dez por cento a partir de janeiro conforme o combinado "
         "com a diretoria na semana passada")
    junto = tr.emendar(a, b)
    for palavra in ("janeiro", "conforme", "diretoria", "semana", "passada"):
        assert palavra in junto, f"perdeu '{palavra}': {junto}"


def test_planejar_pedacos_nao_trava_com_sobreposicao_absurda():
    """Sobreposição >= pedaço fazia o passo virar zero ou negativo: laço infinito,
    e o app congelava sem mensagem nenhuma."""
    partes = tr.planejar_pedacos(600.0, pedaco=10, sobrepor=10)
    assert len(partes) < 500
    assert partes[-1][0] + partes[-1][1] == pytest.approx(600.0)


def test_colar_preserva_ponto_de_abreviacao():
    """'etc.' e 'Dr.' terminam em ponto no meio da frase — tirar o ponto ali
    estraga o texto em vez de arrumar."""
    assert tr.emendar("comprei canetas, papel etc.", "e depois a gente fecha") == \
        "comprei canetas, papel etc. e depois a gente fecha"
    assert tr.emendar("fui atendido pelo Dr.", "silva ontem") == \
        "fui atendido pelo Dr. silva ontem"


def test_nome_livre_nao_pisa_em_arquivo_existente(tmp_path):
    """O dono pode ter 'reuniao.txt' com as anotações dele ao lado do
    'reuniao.mp3'. A transcrição não pode apagar isso."""
    audio = tmp_path / "reuniao.mp3"
    audio.write_bytes(b"x")
    anotacoes = tmp_path / "reuniao.txt"
    anotacoes.write_text("minhas anotações", encoding="utf-8")

    destino = tr.nome_livre(str(audio))
    assert destino != str(anotacoes)
    assert not __import__("os").path.exists(destino)
    assert anotacoes.read_text(encoding="utf-8") == "minhas anotações"


def test_nome_livre_usa_o_nome_simples_quando_esta_vago(tmp_path):
    audio = tmp_path / "entrevista.m4a"
    audio.write_bytes(b"x")
    assert tr.nome_livre(str(audio)).endswith("entrevista.txt")
