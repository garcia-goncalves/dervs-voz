#!/usr/bin/env python3
"""DERVS — a ponte com o DERVS web (o painel de projetos).

O DERVS-VOZ mora no computador do dono; o painel web mora num servidor. Esta
ponte os faz conversar, com três regras que não se negociam:

  1. SÓ SAÍDA. Nada aqui escuta porta: o computador do dono não ganha um endereço
     novo na rede. É o VOZ que vai buscar os recados, nunca o painel que empurra.
  2. O TOKEN É DO ARQUIVO. Usa o mesmo token de "computador pareado" que o
     `agente/enviar.py` do painel já usa (`~/.dervs/agente.json`, ou onde
     `DERVS_AGENTE_ARQUIVO` disser). Nunca entra em log, em `repr` nem em mensagem.
     O cabeçalho só vai para o endereço conferido, e redirecionamento é recusado
     (o urlopen levaria o `Authorization` junto para outro site).
  3. RECADO É DADO, NUNCA ORDEM. O painel pode ser pedido por alguém que invadiu
     a conta. Só `status` e `analisar` em nível `leitura` rodam sozinhos; tudo que
     muda estado vira PROPOSTA no painel do VOZ e só anda com o clique do dono
     aqui (aprovação no painel web não substitui — ver
     `test_dervs_voz_nao_e_senha.py`). O que o porteiro recusa volta `recusado`.

Contrato completo, combinado com a sessão do DERVS web:
`docs/esteira/dervs-integracao-total/contrato-ponte.md`.

Toda falha aqui vira uma frase em português em `ciclo()["motivo"]`: a ponte cair
nunca derruba a voz.
"""
import datetime
import http.client
import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from pathlib import Path

VERSAO = 1
TETO_DA_RESPOSTA = 64 * 1024
TETO_DO_RESUMO = 1000
TETO_DO_TEXTO = 500
MAX_RECADOS_POR_CICLO = 10
MAX_RECADOS_POR_HORA = 60      # teto de trabalho que o painel pode pedir (quem invade a conta não afoga o PC)
PRAZO_DA_RESPOSTA_S = 30       # prazo TOTAL de uma chamada (o timeout do urllib vale por leitura)
ESPERA_DA_REDE_S = 20
ESPERA_CALMA_S = 300           # painel sem a ponte ainda: olha de novo a cada 5 minutos
INTERVALO_PADRAO_S = 60
TETO_DA_ESPERA_S = 900

TIPOS = ("analisar", "status", "propor")
NIVEIS = ("leitura", "muda_estado")
CEREBROS_PEDIDOS = ("auto", "claude_code", "hermes")
_AUTOMATICOS = ("analisar", "status")   # só estes, e só em nível leitura

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
# Nome de projeto: uma palavra. Nada de barra, dois pontos ou `..`.
_PROJETO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class PonteIndisponivel(Exception):
    """A ponte não pode falar agora. A mensagem já está em português para o dono.
    `calma` = situação esperada (o painel ainda não publicou a ponte): tenta de novo
    devagar e sem alarme."""

    def __init__(self, mensagem: str, calma: bool = False):
        super().__init__(mensagem)
        self.calma = calma


def arquivo_do_token() -> Path:
    bruto = os.environ.get("DERVS_AGENTE_ARQUIVO")
    if bruto:
        return Path(bruto).expanduser()
    return Path.home() / ".dervs" / "agente.json"


def conferir_alvo(alvo) -> str:
    """https em qualquer lugar; http só para a própria máquina. Sem usuário na URL."""
    if not isinstance(alvo, str) or not alvo.strip():
        raise PonteIndisponivel("Não há endereço do painel web configurado.")
    p = urllib.parse.urlsplit(alvo.strip())
    if p.scheme not in ("http", "https") or not p.hostname:
        raise PonteIndisponivel("O endereço do painel web precisa começar com https://.")
    if p.username or p.password:
        raise PonteIndisponivel("O endereço do painel web não pode ter usuário nem senha.")
    if p.scheme == "http" and p.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise PonteIndisponivel("Só falo com o painel web por https (http só na própria máquina).")
    return "%s://%s%s" % (p.scheme, p.netloc, p.path.rstrip("/"))


def token_de(alvo: str, arquivo=None) -> str:
    """O token guardado para este painel, ou '' se não há. Nunca levanta."""
    try:
        dados = json.loads(Path(arquivo or arquivo_do_token()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(dados, dict):
        return ""
    for chave, valor in dados.items():
        if isinstance(chave, str) and chave.rstrip("/") == alvo.rstrip("/") \
                and isinstance(valor, dict) and isinstance(valor.get("token"), str):
            return valor["token"]
    return ""


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _agora() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _recortar(texto, limite: int) -> str:
    return str(texto)[:limite]


class PonteWeb:
    def __init__(self, alvo, tratador, *, arquivo_token=None, log=None, estado_fn=None,
                 intervalo_s: float = INTERVALO_PADRAO_S):
        """`tratador` tem `leitura(recado) -> (estado, resumo, custo_usd)` e
        `propor(recado) -> resumo`. Quem decide o que é seguro é ele (porteiro,
        caminhos protegidos); a ponte só garante que nada mais chega a ele."""
        self.alvo = conferir_alvo(alvo)
        self.tratador = tratador
        self._arquivo_token = arquivo_token
        self._estado_fn = estado_fn or (lambda: {})
        self.intervalo_s = intervalo_s
        self.motivo = None
        self._vistos = OrderedDict()
        self._prontos = OrderedDict()   # resultado pronto que o painel ainda não recebeu
        self._marcas = []               # quando cada recado foi aceito (teto por hora)
        self._avisou_teto = False
        self._parar = threading.Event()
        self._thread = None
        if log is None:
            import dervs_log_acoes
            log = dervs_log_acoes.LogAcoes()
        self.log = log
        self._abridor = urllib.request.build_opener(_SemRedirecionar)

    def __repr__(self):
        return "<PonteWeb alvo=%s>" % self.alvo

    @property
    def ligada(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------ rede

    def _falar(self, metodo: str, caminho: str, corpo=None):
        token = token_de(self.alvo, self._arquivo_token)
        if not token:
            raise PonteIndisponivel(
                "Este computador ainda não está pareado com o painel web: falta o token. "
                "Gere um código no painel e rode o pareamento (agente.enviar --codigo).")
        dados = None
        if corpo is not None:
            dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
            if len(dados) > TETO_DA_RESPOSTA:
                raise PonteIndisponivel("O que eu ia mandar ao painel ficou grande demais.")
        pedido = urllib.request.Request(self.alvo + caminho, data=dados, method=metodo)
        pedido.add_header("Authorization", "Token " + token)
        pedido.add_header("Accept", "application/json")
        if dados is not None:
            pedido.add_header("Content-Type", "application/json")
        try:
            with self._abridor.open(pedido, timeout=ESPERA_DA_REDE_S) as r:
                bruto = self._ler_com_prazo(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise PonteIndisponivel(
                    "O painel ainda não tem a ponte com o DERVS-VOZ; tento de novo em alguns "
                    "minutos.", calma=True)
            if e.code in (401, 403):
                raise PonteIndisponivel(
                    "O painel não reconheceu o token deste computador (ou ainda não tem a "
                    "ponte). Se persistir, pareie de novo pelo painel.", calma=True)
            if 300 <= e.code < 400:
                raise PonteIndisponivel(
                    "O painel mandou para outro endereço; não sigo (o token iria junto). "
                    "Confira o endereço configurado.")
            raise PonteIndisponivel("O painel está fora do ar ou com erro (HTTP %d)." % e.code)
        except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError):
            raise PonteIndisponivel("Não alcancei o painel em %s. Sem internet ou fora do ar?"
                                    % self.alvo)
        if len(bruto) > TETO_DA_RESPOSTA:
            raise PonteIndisponivel("A resposta do painel veio grande demais; ignorei.")
        try:
            resposta = json.loads(bruto or b"{}")
        except ValueError:
            raise PonteIndisponivel("O painel respondeu algo que não entendi.")
        return resposta if isinstance(resposta, dict) else {}

    @staticmethod
    def _ler_com_prazo(resposta) -> bytes:
        """Lê em blocos conferindo o relógio: um servidor que goteja 1 byte a cada
        19 s não prende a thread da ponte (o timeout do socket vale por leitura)."""
        limite = time.monotonic() + PRAZO_DA_RESPOSTA_S
        partes, total = [], 0
        while total <= TETO_DA_RESPOSTA:
            if time.monotonic() > limite:
                raise TimeoutError("prazo da resposta estourou")
            bloco = resposta.read(min(4096, TETO_DA_RESPOSTA + 1 - total))
            if not bloco:
                break
            partes.append(bloco)
            total += len(bloco)
        return b"".join(partes)

    def enviar_estado(self):
        # o painel recusa (400) qualquer chave fora das cinco do contrato
        corpo = {"versao": VERSAO, "enviado_em": _agora()}
        corpo.update(self._estado_fn() or {})
        self._falar("POST", "/agente/voz/estado", corpo)

    def buscar_recados(self) -> list:
        lista = self._falar("GET", "/agente/voz/recados").get("recados")
        return lista if isinstance(lista, list) else []

    def devolver(self, resultado: dict):
        self._falar("POST", "/agente/voz/resultado", resultado)

    # ------------------------------------------------------------ recado

    def _validar(self, recado: dict):
        """None se está no contrato; senão, o motivo da recusa."""
        if recado.get("tipo") not in TIPOS:
            return "tipo de recado desconhecido"
        if recado.get("nivel") not in NIVEIS:
            return "nível de recado desconhecido"
        alvo = recado.get("alvo")
        if alvo not in (None, "") and not (isinstance(alvo, str) and _PROJETO.fullmatch(alvo)):
            return "nome de projeto inválido"
        texto = recado.get("texto", "")
        if not isinstance(texto, str) or len(texto) > TETO_DO_TEXTO:
            return "texto grande demais"
        if any(unicodedata.category(c) in ("Cc", "Cf") and c != chr(10) for c in texto):
            return "texto com caractere de controle"
        if recado.get("cerebro_pedido", "auto") not in CEREBROS_PEDIDOS:
            return "cérebro pedido desconhecido"
        return None

    def _registrar(self, evento: str, recado: dict, extra=None):
        dados = {"origem": "painel_web", "id": recado.get("id"), "tipo": recado.get("tipo"),
                 "nivel": recado.get("nivel"), "alvo": recado.get("alvo"),
                 "texto": recado.get("texto")}
        dados.update(extra or {})
        self.log.registrar(evento, dados)

    def _cabe_na_hora(self) -> bool:
        agora = time.monotonic()
        self._marcas = [m for m in self._marcas if agora - m < 3600]
        if len(self._marcas) >= MAX_RECADOS_POR_HORA:
            if not self._avisou_teto:
                self._avisou_teto = True
                self._rastro("alerta", {"motivo": "teto de %d recados por hora; o resto espera"
                                        % MAX_RECADOS_POR_HORA})
            return False
        self._avisou_teto = False
        self._marcas.append(agora)
        return True

    def _rastro(self, evento: str, dados: dict):
        try:
            self.log.registrar(evento, dict(dados, origem="painel_web"))
        except Exception:
            pass

    def processar(self, recado) -> dict | None:
        """Devolve o resultado a enviar, ou None se o recado deve ser ignorado."""
        if not isinstance(recado, dict):
            return None
        rid = recado.get("id")
        if not isinstance(rid, str) or not _ID.fullmatch(rid):
            self._rastro("recusou", {"motivo": "recado sem id válido"})
            return None
        if rid in self._vistos or rid in self._prontos:
            return None
        if not self._cabe_na_hora():
            return None
        self._vistos[rid] = True
        while len(self._vistos) > 500:
            self._vistos.popitem(last=False)

        inicio = datetime.datetime.now()
        cerebro, custo = "claude_code", 0.0
        erro = self._validar(recado)
        try:
            if erro:
                self._registrar("recusou", recado, {"motivo": erro})
                estado, resumo = "recusado", "Recado fora do contrato: " + erro + "."
            elif recado["nivel"] == "leitura" and recado["tipo"] in _AUTOMATICOS:
                self._registrar("analisou", recado)
                estado, resumo, custo = self.tratador.leitura(recado)
            else:
                self._registrar("propos", recado)
                resumo = self.tratador.propor(recado)
                estado = "aguardando_clique"
        except Exception as e:
            # a mensagem real pode ter caminho ou dado: o dono vê o genérico e o
            # registro local guarda só o TIPO do erro
            self._rastro("alerta", {"id": rid, "falha": type(e).__name__})
            estado, resumo = "falhou", "Não consegui concluir este recado."
        if estado not in ("feito", "recusado", "falhou", "aguardando_clique"):
            estado = "falhou"
        try:
            import dervs_log_acoes
            resumo = str(dervs_log_acoes.redigir(str(resumo)))
        except Exception:
            resumo = "Resumo omitido por segurança."
        return {"id": rid, "cerebro": cerebro, "estado": estado,
                "resumo": _recortar(resumo, TETO_DO_RESUMO),
                "custo_usd": float(custo or 0.0),
                "duracao_s": round((datetime.datetime.now() - inicio).total_seconds(), 3),
                "terminado_em": _agora()}

    # ------------------------------------------------------------ ciclo e laço

    def ciclo(self) -> dict:
        """Uma volta: manda o estado, busca recados, responde. Nunca levanta."""
        feitos = 0
        try:
            self.enviar_estado()
            # o que já foi feito mas não chegou ao painel (rede caiu) vai primeiro,
            # sem refazer o trabalho
            for rid in list(self._prontos):
                self.devolver(self._prontos[rid])
                del self._prontos[rid]
            for recado in self.buscar_recados()[:MAX_RECADOS_POR_CICLO]:
                resultado = self.processar(recado)
                if resultado is not None:
                    self._prontos[resultado["id"]] = resultado
                    self.devolver(resultado)
                    del self._prontos[resultado["id"]]
                    feitos += 1
        except PonteIndisponivel as e:
            self.motivo = str(e)
            return {"ok": False, "motivo": self.motivo, "recados": feitos, "calma": e.calma}
        except Exception as e:
            self._rastro("alerta", {"falha": type(e).__name__})
            self.motivo = "Erro inesperado na ponte com o painel web."
            return {"ok": False, "motivo": self.motivo, "recados": feitos}
        self.motivo = None
        return {"ok": True, "motivo": "", "recados": feitos}

    def _laco(self):
        falhas = 0
        while not self._parar.is_set():
            r = self.ciclo()
            falhas = 0 if r["ok"] else falhas + 1
            espera = min(self.intervalo_s * (2 ** min(falhas, 6)), max(TETO_DA_ESPERA_S,
                                                                      self.intervalo_s))
            if r.get("calma"):
                espera = max(ESPERA_CALMA_S, self.intervalo_s)
            self._parar.wait(espera)

    def iniciar(self):
        if self.ligada:
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._laco, name="ponte-web", daemon=True)
        self._thread.start()

    def parar(self, espera_s: float = 5):
        self._parar.set()
        if self._thread is not None:
            self._thread.join(espera_s)


# ---------------------------------------------------------------- ligação ao app

def estado_do_voz() -> dict:
    """O que o VOZ conta ao painel de si mesmo. Só o que o painel pode mostrar sem
    risco: quais cérebros existem, e o gasto do dia. Sem chave, sem caminho."""
    gasto = 0.0
    try:
        import dervs_gasto
        gasto = float(dervs_gasto.total_do_dia().get("total", 0.0))
    except Exception:
        pass
    return {
        "cerebro_ativo": "claude_code",
        "cerebros": {
            "claude_code": {"disponivel": True, "motivo": ""},
            "hermes": {"disponivel": False, "motivo": "ainda não instalado neste computador"},
            "jev": {"disponivel": bool(os.environ.get("TYPESAFE_API_KEY")),
                    "motivo": "" if os.environ.get("TYPESAFE_API_KEY")
                    else "sem a chave TYPESAFE_API_KEY (acesso por lista de espera)"},
        },
        "gasto_dia_usd": round(gasto, 4),
    }


def iniciar_da_config(conf: dict, *, tratador=None, log=None):
    """Liga a ponte se a configuração pede e há token. Devolve `(ponte, motivo)`;
    `ponte` é None quando não liga, e `motivo` diz por quê. Nunca levanta."""
    try:
        if not conf.get("ponte_web_ligada", True):
            return None, "a ponte com o painel web está desligada na configuração"
        alvo = conferir_alvo(conf.get("ponte_web_alvo"))
        if not token_de(alvo):
            return None, ("este computador ainda não está pareado com %s (falta o token)" % alvo)
        if tratador is None:
            import dervs_ponte_tratador
            tratador = dervs_ponte_tratador.TratadorLocal(estado_fn=estado_do_voz)
        ponte = PonteWeb(alvo, tratador, log=log, estado_fn=estado_do_voz,
                         intervalo_s=float(conf.get("ponte_web_intervalo_s", INTERVALO_PADRAO_S)))
        ponte.iniciar()
        return ponte, ""
    except PonteIndisponivel as e:
        return None, str(e)
    except Exception:
        return None, "a ponte com o painel web não pôde ser iniciada"
