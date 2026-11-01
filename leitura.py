"""Leitura do deck DESSEM D31.

Cada função lê um arquivo do deck e devolve listas e dicionários simples.
As colunas são contadas a partir de 1, como no Manual do Usuário do DESSEM.
Listas por período têm 336 valores: a posição 0 é a meia hora 31/10 00:00.

Para conferir os dados lidos: python leitura.py
"""
import struct
from datetime import datetime
from pathlib import Path

PASTA_DECK = Path(__file__).parent / "DS_CCEE_112026_SEMREDE_RV0D31"

# Usinas do estudo (números do cadastro)
TERMICAS = {"ANGRA1": (1, 1), "BAIXADA": (211, 3)}    # nome: (usina, unidade equivalente)
HIDRELETRICAS = {"FURNAS": 6, "MORAES": 7}
MONTANTE_FURNAS = [1, 2, 4]                            # Camargos, Itutinga e Funil-Grande

MEIAS_HORAS_POR_DIA = 48


# =========================================================== funções auxiliares
def ler_linhas(arquivo):
    caminho = PASTA_DECK / arquivo
    return caminho.read_text(encoding="latin-1").splitlines()


def campo(linha, coluna_inicial, coluna_final):
    """Texto entre duas colunas (contadas a partir de 1, como no manual)."""
    return linha[coluna_inicial - 1:coluna_final].strip()


def encontrar_linha(linhas, inicio_do_texto):
    """Posição da primeira linha que começa com o texto dado."""
    for posicao, linha in enumerate(linhas):
        if linha.startswith(inicio_do_texto):
            return posicao


def registros_do_bloco(linhas, nome_do_bloco):
    """Linhas entre o cabeçalho de um bloco (ex.: INIT) e o FIM seguinte, sem comentários (&)."""
    registros = []
    dentro_do_bloco = False
    for linha in linhas:
        if linha.strip() == nome_do_bloco:
            dentro_do_bloco = True
        elif dentro_do_bloco and linha.startswith("FIM"):
            break
        elif dentro_do_bloco and linha.strip() != "" and not linha.startswith("&"):
            registros.append(linha)
    return registros


def periodo(dias, dia, hora, meia_hora):
    """Posição (0 a 335) da meia hora que começa em dia/hora/meia hora."""
    return dias.index(dia) * MEIAS_HORAS_POR_DIA + hora * 2 + meia_hora


def cota(polinomio, volume):
    """Cota (m) pelo polinômio cota x volume do hidr.dat: a0 + a1 V + a2 V² + a3 V³ + a4 V⁴."""
    return sum(polinomio[k] * volume ** k for k in range(5))


def volume_da_cota(polinomio, cota_desejada, vmin, vmax):
    """Volume em que a cota vale cota_desejada (bisseção entre vmin e vmax)."""
    baixo, alto = vmin, vmax
    for _ in range(100):
        meio = (baixo + alto) / 2
        if cota(polinomio, meio) < cota_desejada:
            baixo = meio
        else:
            alto = meio
    return alto


# =========================================================== entdados.dat
def ler_horizonte(entdados):
    """Registro TM: dias do estudo (31, 1, 2, ..., 6) e número de meias horas (336)."""
    dias = []
    horas = 0.0
    for linha in entdados:
        if linha.startswith("TM "):
            dia = int(campo(linha, 5, 6))
            if dia not in dias:
                dias.append(dia)
            horas += float(campo(linha, 20, 24))      # duração do intervalo
    return dias, int(horas * 2)


def ler_demanda(entdados, dias, T):
    """Registro DP do subsistema 1 (SE), em MW. Cada registro vale do seu início até o
    próximo: no dia 31 há um valor por meia hora; nos outros dias, um por patamar."""
    valor_no_inicio = {}
    for linha in entdados:
        if linha.startswith("DP ") and int(campo(linha, 5, 6)) == 1:
            dia = int(campo(linha, 9, 10))
            hora = int(campo(linha, 12, 13))
            meia_hora = int(campo(linha, 15, 15))
            valor_no_inicio[periodo(dias, dia, hora, meia_hora)] = float(campo(linha, 25, 34))

    demanda = []
    valor = None
    for t in range(T):
        if t in valor_no_inicio:
            valor = valor_no_inicio[t]
        demanda.append(valor)
    return demanda


def ler_custo_deficit(entdados):
    """Registro CD do subsistema 1, em R$/MWh."""
    for linha in entdados:
        if linha.startswith("CD ") and int(campo(linha, 4, 5)) == 1:
            return float(campo(linha, 26, 35))


def ler_volume_inicial(entdados):
    """Registro UH: volume inicial de cada usina, em % do volume útil."""
    volume = {}
    for linha in entdados:
        if linha.startswith("UH "):
            volume[int(campo(linha, 5, 7))] = float(campo(linha, 30, 39))
    return volume


# =========================================================== térmicas
def ler_trajetoria(rampas, usina, unidade, sentido):
    """rampas.dat: potência (MW) em cada meia hora da partida (sentido A) ou da parada (D).
    O ponto k = 2 x Tempo + meia hora. Ponto faltando repete o anterior. Na parada, o
    último ponto (0 MW) já é a unidade desligada e fica de fora."""
    pontos = {}
    for linha in rampas:
        if (int(campo(linha, 1, 3)) == usina and int(campo(linha, 5, 7)) == unidade
                and campo(linha, 18, 18) == sentido):
            k = 2 * int(campo(linha, 32, 36)) + int(campo(linha, 38, 38))
            pontos[k] = float(campo(linha, 21, 30))

    if sentido == "D" and pontos[max(pontos)] == 0:
        del pontos[max(pontos)]

    trajetoria = []
    for k in range(1, max(pontos) + 1):
        if k in pontos:
            trajetoria.append(pontos[k])
        else:
            trajetoria.append(trajetoria[-1])
    return trajetoria


def ler_termicas():
    termdat = ler_linhas("termdat.dat")
    operut = ler_linhas("operut.dat")
    init = registros_do_bloco(operut, "INIT")
    oper = registros_do_bloco(operut, "OPER")
    rampas = registros_do_bloco(ler_linhas("rampas.dat"), "RAMP")

    termicas = {}
    for nome, (usina, unidade) in TERMICAS.items():
        ut = {}

        # termdat.dat, CADUNIDT: potências e tempos mínimos da unidade
        for linha in termdat:
            if (linha.startswith("CADUNIDT") and int(campo(linha, 10, 12)) == usina
                    and int(campo(linha, 14, 15)) == unidade):
                ut["pmax"] = float(campo(linha, 34, 43))
                ut["pmin"] = float(campo(linha, 45, 54))
                ut["ton_h"] = float(campo(linha, 56, 60))
                ut["toff_h"] = float(campo(linha, 62, 66))

        # operut.dat, INIT: ligada ou não e geração no início
        for linha in init:
            if int(campo(linha, 1, 3)) == usina and int(campo(linha, 19, 21)) == unidade:
                ut["ligada_inicio"] = int(campo(linha, 25, 26))
                ut["geracao_inicio"] = float(campo(linha, 30, 39))

        # operut.dat, OPER: custo variável unitário (R$/MWh)
        for linha in oper:
            if int(campo(linha, 1, 3)) == usina and int(campo(linha, 18, 19)) == unidade:
                ut["cvu"] = float(campo(linha, 57, 66))

        ut["trajetoria_partida"] = ler_trajetoria(rampas, usina, unidade, "A")
        ut["trajetoria_parada"] = ler_trajetoria(rampas, usina, unidade, "D")
        termicas[nome] = ut
    return termicas


# =========================================================== hidrelétricas
def ler_cadastro_hidr(hidr, usina):
    """hidr.dat: registro binário de 832 bytes por usina, na ordem do número da usina."""
    inicio = (usina - 1) * 832
    vmin, vmax = struct.unpack_from("<2f", hidr, inicio + 40)
    return {
        "vmin": vmin,                                                        # hm³
        "vmax": vmax,                                                        # hm³
        "polinomio_cota": struct.unpack_from("<5d", hidr, inicio + 64),
        "maquinas": struct.unpack_from("<5i", hidr, inicio + 196),           # máquinas por conjunto
        "vazao_maquina": struct.unpack_from("<5i", hidr, inicio + 556),      # m³/s por máquina
        "prod_especifica": struct.unpack_from("<f", hidr, inicio + 576)[0],  # MW/(m³/s)/m
        "canal_fuga": struct.unpack_from("<f", hidr, inicio + 732)[0],       # cota de jusante (m)
    }


def ler_vazoes():
    """dadvaz.dat: vazão incremental diária (m³/s) por (usina, dia)."""
    linhas = ler_linhas("dadvaz.dat")
    primeira = encontrar_linha(linhas, "VAZOES DIARIAS") + 3       # pula título e cabeçalho
    vazoes = {}
    for linha in linhas[primeira:]:
        if linha.startswith("FIM"):
            break
        usina = int(campo(linha, 1, 3))
        dia = int(campo(linha, 25, 26))
        vazoes[usina, dia] = float(campo(linha, 45, 53))
    return vazoes


def vazao_por_dia(vazoes, usina, dias):
    """Uma vazão por dia. Dia sem registro repete o anterior (o registro vale até o próximo)."""
    valores = []
    for dia in dias:
        if (usina, dia) in vazoes:
            valores.append(vazoes[usina, dia])
        else:
            valores.append(valores[-1])
    return valores


def instante_operuh(linha, coluna_dia, dias, T):
    """Campo dia/hora/meia hora de um registro LIM convertido em período.
    'I' é o início do estudo e 'F' é o fim."""
    dia = campo(linha, coluna_dia, coluna_dia + 1)
    if dia == "I":
        return 0
    if dia == "F":
        return T
    hora = int(campo(linha, coluna_dia + 3, coluna_dia + 4))
    meia_hora = int(campo(linha, coluna_dia + 6, coluna_dia + 6))
    return periodo(dias, int(dia), hora, meia_hora)


def limite_operuh(operuh, restricao, lado, dias, T):
    """operuh.dat, registros LIM: valor do limite em cada período (None = sem limite).
    lado = "inferior" (colunas 39-48) ou "superior" (colunas 49-58)."""
    valores = [None] * T
    for linha in operuh:
        if linha.startswith("OPERUH LIM") and campo(linha, 15, 19) == restricao:
            if lado == "inferior":
                texto = campo(linha, 39, 48)
            else:
                texto = campo(linha, 49, 58)
            if texto != "":
                inicio = instante_operuh(linha, 21, dias, T)
                fim = instante_operuh(linha, 29, dias, T)
                for t in range(inicio, fim):
                    valores[t] = float(texto)
    return valores


def ler_hidreletricas(entdados, dias, T):
    hidr = (PASTA_DECK / "hidr.dat").read_bytes()
    operuh = ler_linhas("operuh.dat")
    volume_inicial_pct = ler_volume_inicial(entdados)
    vazoes = ler_vazoes()

    hidros = {}
    for nome, usina in HIDRELETRICAS.items():
        uh = ler_cadastro_hidr(hidr, usina)
        uh["v0"] = uh["vmin"] + volume_inicial_pct[usina] / 100 * (uh["vmax"] - uh["vmin"])

        # engolimento máximo: soma de (máquinas x vazão por máquina) dos conjuntos
        uh["qmax"] = 0
        for n_maquinas, vazao in zip(uh["maquinas"], uh["vazao_maquina"]):
            uh["qmax"] += n_maquinas * vazao

        # produtibilidade constante: específica x queda no volume inicial (sem perdas)
        queda = cota(uh["polinomio_cota"], uh["v0"]) - uh["canal_fuga"]
        uh["rho"] = uh["prod_especifica"] * queda
        hidros[nome] = uh

    furnas = hidros["FURNAS"]
    moraes = hidros["MORAES"]

    # Afluências (m³/s), constantes ao longo de cada dia.
    # Furnas recebe a vazão natural de toda a cadeia a montante; Moraes, só a sua incremental.
    afluencia_furnas = vazao_por_dia(vazoes, 6, dias)
    for usina in MONTANTE_FURNAS:
        montante = vazao_por_dia(vazoes, usina, dias)
        afluencia_furnas = [a + b for a, b in zip(afluencia_furnas, montante)]
    afluencia_moraes = vazao_por_dia(vazoes, 7, dias)
    furnas["afluencia"] = [afluencia_furnas[t // MEIAS_HORAS_POR_DIA] for t in range(T)]
    moraes["afluencia"] = [afluencia_moraes[t // MEIAS_HORAS_POR_DIA] for t in range(T)]

    # Restrições operativas do operuh.dat
    furnas["defluencia_min"] = limite_operuh(operuh, "00443", "inferior", dias, T)
    ate_01_11 = limite_operuh(operuh, "11145", "superior", dias, T)
    depois_01_11 = limite_operuh(operuh, "11394", "superior", dias, T)
    furnas["defluencia_max"] = [a if a is not None else b for a, b in zip(ate_01_11, depois_01_11)]
    furnas["vertimento_max"] = limite_operuh(operuh, "10186", "superior", dias, T)
    furnas["volume_min"] = furnas["vmin"]

    moraes["defluencia_min"] = limite_operuh(operuh, "00445", "inferior", dias, T)
    moraes["defluencia_max"] = [None] * T
    moraes["vertimento_max"] = [None] * T
    cota_minima = limite_operuh(operuh, "00444", "inferior", dias, T)[0]
    volume_cota_minima = volume_da_cota(moraes["polinomio_cota"], cota_minima, moraes["vmin"], moraes["vmax"])
    moraes["volume_min"] = max(moraes["vmin"], volume_cota_minima)
    return hidros


# =========================================================== tudo junto
def ler_data_inicio():
    """Cabeçalho do dadvaz.dat: hora, dia, mês e ano do início do estudo."""
    linhas = ler_linhas("dadvaz.dat")
    posicao = encontrar_linha(linhas, "Hr  Dd  Mm  Ano")
    hora, dia, mes, ano = linhas[posicao + 2].split()
    return datetime(int(ano), int(mes), int(dia), int(hora))


def ler_dados():
    entdados = ler_linhas("entdados.dat")
    dias, T = ler_horizonte(entdados)
    return {
        "inicio": ler_data_inicio(),
        "dias": dias,
        "T": T,
        "demanda_se": ler_demanda(entdados, dias, T),
        "custo_deficit": ler_custo_deficit(entdados),
        "termicas": ler_termicas(),
        "hidreletricas": ler_hidreletricas(entdados, dias, T),
    }


if __name__ == "__main__":
    dados = ler_dados()
    print("Início:", dados["inicio"], "| dias:", dados["dias"], "| períodos:", dados["T"])
    print("Demanda do SE (MW): mín", min(dados["demanda_se"]), "máx", max(dados["demanda_se"]))
    print("Custo de déficit (R$/MWh):", dados["custo_deficit"])
    for nome, ut in dados["termicas"].items():
        print(nome, ut)
    for nome, uh in dados["hidreletricas"].items():
        print(f"{nome}: Vmin {uh['vmin']:.1f}, Vmax {uh['vmax']:.1f}, V0 {uh['v0']:.1f}, "
              f"volume mínimo {uh['volume_min']:.1f} hm³, qmax {uh['qmax']} m³/s, rho {uh['rho']:.4f}, "
              f"afluência no 1º dia {uh['afluencia'][0]} m³/s")
