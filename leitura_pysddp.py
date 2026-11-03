"""Adapta os dados do deck DESSEM lidos pela PySDDP ao despacho reduzido."""

import sys
from pathlib import Path


RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "PySDDP-master"))

from PySDDP.dessem.script.cadterm import CadTerm
from PySDDP.dessem.script.dadger import Dadger
from PySDDP.dessem.script.dadvaz import DadVaz
from PySDDP.dessem.script.hidr import Hidr
from PySDDP.dessem.script.operuh import Operuh
from PySDDP.dessem.script.operut import Operut
from PySDDP.dessem.script.rampas import Rampas


PASTA_DECK = RAIZ / "DS_CCEE_112026_SEMREDE_RV0D31"
TERMICAS = {"ANGRA1": (1, 1), "BAIXADA": (211, 3)}
HIDRELETRICAS = {"FURNAS": 6, "MORAES": 7}
MONTANTE_FURNAS = (1, 2, 4)
MEIAS_HORAS_POR_DIA = 48


def registros(colunas):
    """Itera pelas linhas dos dicionários de colunas da PySDDP."""
    return (dict(zip(colunas, valores)) for valores in zip(*colunas.values()))


def instante(dias, dia, hora, meia_hora, total):
    dia = str(dia).strip()
    if dia == "I":
        return 0
    if dia == "F":
        return total
    return dias.index(int(dia)) * MEIAS_HORAS_POR_DIA + int(hora) * 2 + int(meia_hora)


def numero(valor):
    return float(str(valor).strip())


def limite(operuh, indice, lado, dias, total):
    valores = [None] * total
    for linha in registros(operuh.lim):
        if str(linha["ind"]).strip() != indice:
            continue
        texto = str(linha["vmin" if lado == "inferior" else "vmax"]).strip()
        if texto:
            inicio = instante(dias, linha["di"], linha["hi"], linha["mi"], total)
            fim = instante(dias, linha["df"], linha["hf"], linha["mf"], total)
            valores[inicio:fim] = [float(texto)] * (fim - inicio)
    return valores


def trajetoria(rampas, usina, unidade, sentido):
    pontos = {}
    for linha in registros(rampas.rampas):
        if (int(linha["us"]) == usina and int(linha["uni"]) == unidade
                and str(linha["T"]).strip() == sentido):
            posicao = 2 * int(linha["Tempo"]) + int(linha["FlagMeiaHora"])
            pontos[posicao] = numero(linha["Potencia"])
    if sentido == "D" and pontos[max(pontos)] == 0:
        del pontos[max(pontos)]
    valores = []
    for posicao in range(1, max(pontos) + 1):
        valores.append(pontos.get(posicao, valores[-1] if valores else None))
    return valores


def cota(polinomio, volume):
    return sum(coeficiente * volume ** grau for grau, coeficiente in enumerate(polinomio))


def volume_da_cota(polinomio, cota_desejada, vmin, vmax):
    baixo, alto = vmin, vmax
    for _ in range(100):
        meio = (baixo + alto) / 2
        if cota(polinomio, meio) < cota_desejada:
            baixo = meio
        else:
            alto = meio
    return alto


def ler_dados():
    dadger = Dadger()
    dadger.ler(str(PASTA_DECK / "entdados.dat"))
    cadterm = CadTerm()
    cadterm.ler(str(PASTA_DECK / "termdat.dat"))
    operut = Operut()
    operut.ler(str(PASTA_DECK / "operut.dat"))
    rampas = Rampas()
    rampas.ler(str(PASTA_DECK / "rampas.dat"))
    hidr = Hidr()
    hidr.ler(str(PASTA_DECK / "hidr.dat"), tamanho_registro=832)
    dadvaz = DadVaz()
    dadvaz.ler(str(PASTA_DECK / "dadvaz.dat"))
    operuh = Operuh()
    operuh.ler(str(PASTA_DECK / "operuh.dat"))

    dias = []
    duracao = 0.0
    for linha in registros(dadger.tm):
        dia = int(linha["dd"])
        if dia not in dias:
            dias.append(dia)
        duracao += numero(linha["durac"])
    total = int(duracao * 2)

    demanda_inicial = {}
    for linha in registros(dadger.dp):
        if int(linha["ss"]) == 1:
            posicao = instante(dias, linha["di"], linha["hi"], linha["mi"], total)
            demanda_inicial[posicao] = numero(linha["demanda"])
    demanda = []
    valor = None
    for posicao in range(total):
        valor = demanda_inicial.get(posicao, valor)
        demanda.append(valor)

    custo_deficit = next(numero(linha["custo"]) for linha in registros(dadger.cd)
                         if int(linha["is"]) == 1)
    volumes_pct = {int(linha["ind"]): numero(linha["vinic"])
                   for linha in registros(dadger.uh)}

    cadastro_termico = {(int(linha["num_usi"]), int(linha["ind_ger"])): linha
                        for linha in registros(cadterm.cadunidt)}
    iniciais = {(int(linha["us"]), int(linha["ug"])): linha
                for linha in registros(operut.condicoes_iniciais)}
    custos = {(int(linha["us"]), int(linha["un"])): linha
              for linha in registros(operut.limites_condicoes)}
    termicas = {}
    for nome, chave in TERMICAS.items():
        cadastro = cadastro_termico[chave]
        inicial = iniciais[chave]
        operacao = custos[chave]
        termicas[nome] = {
            "pmax": numero(cadastro["pot"]),
            "pmin": numero(cadastro["ger_min"]),
            "ton_h": numero(cadastro["temp_on"]),
            "toff_h": numero(cadastro["temp_off"]),
            "ligada_inicio": int(inicial["st"]),
            "geracao_inicio": numero(inicial["GerInic"]),
            "cvu": numero(operacao["Custo"]),
            "trajetoria_partida": trajetoria(rampas, *chave, "A"),
            "trajetoria_parada": trajetoria(rampas, *chave, "D"),
        }

    vazoes = {(int(linha["num"]), int(linha["di"])): numero(linha["vazao"])
              for linha in registros(dadvaz.vazoes_diarias)}

    def vazao_diaria(usina):
        valores = []
        for dia in dias:
            valores.append(vazoes.get((usina, dia), valores[-1] if valores else None))
        return valores

    hidros = {}
    for nome, usina in HIDRELETRICAS.items():
        indice = hidr.codigo["valor"].index(usina)
        vmin = hidr.vol_min["valor"][indice]
        vmax = hidr.vol_max["valor"][indice]
        v0 = vmin + volumes_pct[usina] / 100 * (vmax - vmin)
        polinomio = hidr.pol_cota_vol["valor"][indice]
        queda = cota(polinomio, v0) - hidr.cfmed["valor"][indice]
        hidros[nome] = {
            "vmin": vmin,
            "vmax": vmax,
            "polinomio_cota": polinomio,
            "maquinas": hidr.maq_por_conj["valor"][indice],
            "vazao_maquina": hidr.vaz_efet_conj["valor"][indice],
            "prod_especifica": hidr.prod_esp["valor"][indice],
            "canal_fuga": hidr.cfmed["valor"][indice],
            "v0": v0,
            "qmax": sum(n * q for n, q in zip(hidr.maq_por_conj["valor"][indice],
                                            hidr.vaz_efet_conj["valor"][indice])),
            "rho": hidr.prod_esp["valor"][indice] * queda,
        }

    afluencia_furnas = [sum(valores) for valores in zip(
        vazao_diaria(6), *(vazao_diaria(usina) for usina in MONTANTE_FURNAS))]
    afluencia_moraes = vazao_diaria(7)
    hidros["FURNAS"]["afluencia"] = [afluencia_furnas[t // MEIAS_HORAS_POR_DIA]
                                      for t in range(total)]
    hidros["MORAES"]["afluencia"] = [afluencia_moraes[t // MEIAS_HORAS_POR_DIA]
                                      for t in range(total)]

    furnas = hidros["FURNAS"]
    moraes = hidros["MORAES"]
    furnas["defluencia_min"] = limite(operuh, "00443", "inferior", dias, total)
    antes = limite(operuh, "11145", "superior", dias, total)
    depois = limite(operuh, "11394", "superior", dias, total)
    furnas["defluencia_max"] = [a if a is not None else b for a, b in zip(antes, depois)]
    furnas["vertimento_max"] = limite(operuh, "10186", "superior", dias, total)
    furnas["volume_min"] = furnas["vmin"]
    moraes["defluencia_min"] = limite(operuh, "00445", "inferior", dias, total)
    moraes["defluencia_max"] = [None] * total
    moraes["vertimento_max"] = [None] * total
    cota_minima = limite(operuh, "00444", "inferior", dias, total)[0]
    moraes["volume_min"] = max(moraes["vmin"], volume_da_cota(
        moraes["polinomio_cota"], cota_minima, moraes["vmin"], moraes["vmax"]))

    return {
        "inicio": dadvaz.data_hora.to_pydatetime(),
        "dias": dias,
        "T": total,
        "demanda_se": demanda,
        "custo_deficit": custo_deficit,
        "termicas": termicas,
        "hidreletricas": hidros,
    }


if __name__ == "__main__":
    dados = ler_dados()
    print("Início:", dados["inicio"], "| períodos:", dados["T"])
    print("Térmicas:", dados["termicas"])
    print("Hidrelétricas:", list(dados["hidreletricas"]))
