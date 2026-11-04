"""Servidor local da interface do despacho. Execute: python server.py"""

import json
import math
import threading
from time import perf_counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from despacho import AJUSTES_PADRAO, DT, executar_despacho
from leitura_pysddp import TERMICAS_PADRAO, ler_dados


RAIZ = Path(__file__).resolve().parent
DADOS_BASE = ler_dados()
LIMITES_BASE = {
    "demanda": (0.7, 1.3),
    "custo_deficit": (0.5, 2.0),
    "afluencia_furnas": (0.5, 1.5),
    "afluencia_moraes": (0.5, 1.5),
    "rampa": (0.1, 0.4),
    "custo_vertimento": (0.0, 1.0),
}
ARQUIVOS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/chart.css": ("chart.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
TRAVA = threading.Lock()
CACHE = {}


def metadados_termicas():
    return [{
        "id": identificador, "nome": dados["nome"], "rotulo": dados["rotulo"],
        "codigo_usina": dados["codigo_usina"], "unidade": dados["unidade"],
        "cvu": dados["cvu"], "ton_h": dados["ton_h"], "toff_h": dados["toff_h"],
        "pmin": dados["pmin"], "pmax": dados["pmax"],
    } for identificador, dados in DADOS_BASE["termicas"].items()]


def validar_termicas(recebidas):
    if not isinstance(recebidas, list) or len(recebidas) != 2 or len(set(recebidas)) != 2:
        raise ValueError("Selecione exatamente duas UTEs diferentes.")
    if any(nome not in DADOS_BASE["termicas"] for nome in recebidas):
        raise ValueError("Sele\u00e7\u00e3o de UTE inv\u00e1lida.")
    return tuple(recebidas)


def ajustes_e_limites(termicas):
    ajustes = dict(AJUSTES_PADRAO)
    limites = dict(LIMITES_BASE)
    for nome in termicas:
        dados = DADOS_BASE["termicas"][nome]
        sufixo = nome.lower()
        ajustes[f"cvu_{sufixo}"] = 1.0
        ajustes[f"ton_{sufixo}"] = dados["ton_h"]
        ajustes[f"toff_{sufixo}"] = dados["toff_h"]
        limites[f"cvu_{sufixo}"] = (0.5, 1.5)
        limites[f"ton_{sufixo}"] = (0.0, max(336.0, dados["ton_h"]))
        limites[f"toff_{sufixo}"] = (0.0, max(336.0, dados["toff_h"]))
    return ajustes, limites


def validar_ajustes(recebidos, termicas):
    padroes, limites = ajustes_e_limites(termicas)
    if not isinstance(recebidos, dict) or set(recebidos) != set(padroes):
        raise ValueError("Envie todos os parâmetros do cenário.")
    ajustes = {}
    for chave, (minimo, maximo) in limites.items():
        valor = recebidos[chave]
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
            raise ValueError(f"Valor inválido para {chave}.")
        if not minimo <= valor <= maximo:
            raise ValueError(f"{chave} deve estar entre {minimo} e {maximo}.")
        ajustes[chave] = float(valor)
    return ajustes


def resposta_despacho(ajustes, termicas, efeito_fim_mundo=False):
    chave = termicas + (efeito_fim_mundo,) + tuple((nome, ajustes[nome]) for nome in sorted(ajustes))
    if chave not in CACHE:
        inicio = perf_counter()
        solucao = executar_despacho(
            ajustes=ajustes, salvar=False, dados_base=DADOS_BASE,
            termicas_selecionadas=termicas,
            efeito_fim_mundo=efeito_fim_mundo,
        )
        tabela = solucao["resultado"]
        if len(CACHE) >= 12:
            CACHE.pop(next(iter(CACHE)))
        CACHE[chave] = {
            "status": solucao["status"],
            "status_lp": solucao["status_lp"],
            "custo": float(solucao["custo"]),
            "gap": float(solucao["gap"]),
            "tempo_s": round(perf_counter() - inicio, 3),
            "linhas": json.loads(tabela.to_json(orient="records")),
            "resumo": {
                "energia_hidraulica": float(sum(tabela[f"gh_{h}"].sum() for h in ("FURNAS", "MORAES")) * DT),
                "energia_termica": float(sum(tabela[f"gt_{u}"].sum() for u in termicas) * DT),
                "energia_deficit": float(tabela["deficit"].sum() * DT),
                "cmo_medio": float(tabela["cmo"].mean()),
                "cmo_maximo": float(tabela["cmo"].max()),
            },
            "termicas": [{"id": nome, "nome": DADOS_BASE["termicas"][nome]["nome"]}
                         for nome in termicas],
        }
    return CACHE[chave]


class Handler(BaseHTTPRequestHandler):
    def enviar_json(self, valor, codigo=200):
        conteudo = json.dumps(valor, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(conteudo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(conteudo)

    def do_GET(self):
        caminho = urlsplit(self.path).path
        if caminho == "/api/config":
            ajustes, limites = ajustes_e_limites(TERMICAS_PADRAO)
            self.enviar_json({"ajustes": ajustes, "limites": limites,
                             "termicas": metadados_termicas(),
                             "termicas_padrao": TERMICAS_PADRAO,
                             "periodos": DADOS_BASE["T"], "inicio": DADOS_BASE["inicio"].isoformat()})
            return
        arquivo = ARQUIVOS.get(caminho)
        if arquivo is None:
            self.send_error(404)
            return
        conteudo = (RAIZ / arquivo[0]).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", arquivo[1])
        self.send_header("Content-Length", str(len(conteudo)))
        self.end_headers()
        self.wfile.write(conteudo)

    def do_POST(self):
        if urlsplit(self.path).path != "/api/dispatch":
            self.send_error(404)
            return
        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
            if not 0 < tamanho <= 4096:
                raise ValueError("Tamanho de requisição inválido.")
            corpo = json.loads(self.rfile.read(tamanho))
            termicas = validar_termicas(corpo.get("termicas"))
            ajustes = validar_ajustes(corpo.get("ajustes"), termicas)
            efeito_fim_mundo = corpo.get("efeito_fim_mundo", False)
            if not isinstance(efeito_fim_mundo, bool):
                raise ValueError("Efeito de fim de mundo deve ser verdadeiro ou falso.")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as erro:
            self.enviar_json({"error": str(erro)}, 400)
            return
        if not TRAVA.acquire(blocking=False):
            self.enviar_json({"error": "Otimização em andamento. Aguardando para tentar novamente."}, 409)
            return
        try:
            self.enviar_json(resposta_despacho(ajustes, termicas, efeito_fim_mundo))
        except Exception as erro:
            self.enviar_json({"error": f"Falha na otimização: {erro}"}, 500)
        finally:
            TRAVA.release()


if __name__ == "__main__":
    servidor = ThreadingHTTPServer(("127.0.0.1", 8001), Handler)
    print("Interface disponível em http://127.0.0.1:8001", flush=True)
    servidor.serve_forever()
