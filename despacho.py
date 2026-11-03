"""Despacho hidrotérmico reduzido a partir do deck DESSEM D31.

Usinas: Angra 1 e Baixada Fluminense (térmicas); Furnas -> Mascarenhas de Moraes (cascata).
Barra única, 336 meias horas (31/10 a 06/11). Equações da seção 10 do Manual de
Metodologia do DESSEM.

Etapas:
  1. ler os dados do deck com PySDDP (leitura_pysddp.py)
  2. montar o MILP: variáveis, restrições e função objetivo
  3. resolver
  4. calcular o CMO
  5. salvar os resultados em saida/despacho.csv
"""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pandas as pd
from pyscipopt import Model, SCIP_PARAMSETTING, quicksum

from leitura_pysddp import ler_dados

# Premissas definidas para o estudo (não estão no deck)
DT = 0.5                    # duração de cada período (h)
HM3 = 3600 * DT / 1e6       # 1 m³/s durante meia hora = 0,0018 hm³
K_DEMANDA = 0.04533         # escala da demanda do SE para o parque de quatro usinas de (38 a 54 mil MW) para a escala das 4 usinas (1.716 a 2.433 MW)
FRACAO_RAMPA = 0.20         # rampa por meia hora = 20% de (Pmax - Pmin)
CUSTO_VERTIMENTO = 0.2      # R$/hm³


AJUSTES_PADRAO = {
    "demanda": 1.0,
    "custo_deficit": 1.0,
    "afluencia_furnas": 1.0,
    "afluencia_moraes": 1.0,
    "cvu_angra1": 1.0,
    "cvu_baixada": 1.0,
    "ton_angra1": 168.0,
    "toff_angra1": 168.0,
    "ton_baixada": 72.0,
    "toff_baixada": 48.0,
    "rampa": FRACAO_RAMPA,
    "custo_vertimento": CUSTO_VERTIMENTO,
}


def executar_despacho(ajustes=None, salvar=False, dados_base=None):
    """Resolve o mesmo MILP para um cenário; sem ajustes, usa os dados originais."""
    ajustes = {**AJUSTES_PADRAO, **(ajustes or {})}
    # ===================================================================== 1. dados
    dados = deepcopy(dados_base) if dados_base is not None else ler_dados()
    # Ajustes de cenário são aplicados somente aos dados, antes da montagem do modelo.
    dados["demanda_se"] = [valor * ajustes["demanda"] for valor in dados["demanda_se"]]
    dados["custo_deficit"] *= ajustes["custo_deficit"]
    for nome in ("FURNAS", "MORAES"):
        hidro = dados["hidreletricas"][nome]
        hidro["afluencia"] = [valor * ajustes[f"afluencia_{nome.lower()}"]
                               for valor in hidro["afluencia"]]
    for nome in ("ANGRA1", "BAIXADA"):
        dados["termicas"][nome]["cvu"] *= ajustes[f"cvu_{nome.lower()}"]
        dados["termicas"][nome]["ton_h"] = ajustes[f"ton_{nome.lower()}"]
        dados["termicas"][nome]["toff_h"] = ajustes[f"toff_{nome.lower()}"]
    T = dados["T"]
    PERIODOS = range(1, T + 1)                   # t = 1, ..., 336
    termicas = dados["termicas"]
    hidros = dados["hidreletricas"]
    demanda = [K_DEMANDA * d for d in dados["demanda_se"]]     # demanda[t - 1] é a do período t

    m = Model("despacho")

    # ===================================================================== 2. variáveis
    # gt[i,t]  geração térmica (MW)               u[i,t]  1 se a unidade está ligada
    # y[i,t]   1 se a unidade parte em t          w[i,t]  1 se a unidade para em t
    # q[h,t]   vazão turbinada (m³/s)             s[h,t]  vazão vertida (m³/s)
    # V[h,t]   volume no início do período (hm³)  deficit[t]  déficit (MW)
    gt, u, y, w = {}, {}, {}, {}
    for i in termicas:
        for t in PERIODOS:
            gt[i, t] = m.addVar(lb=0)
            u[i, t] = m.addVar(vtype="B")
            y[i, t] = m.addVar(lb=0, ub=1)       # sai inteira pela (10.5)
            w[i, t] = m.addVar(vtype="B")
        # estado antes do horizonte (t = 0): são números, não variáveis
        u[i, 0] = termicas[i]["ligada_inicio"]
        gt[i, 0] = termicas[i]["geracao_inicio"]

    q, s, V = {}, {}, {}
    for h in hidros:
        V[h, 1] = hidros[h]["v0"]               # volume inicial: número
        for t in PERIODOS:
            q[h, t] = m.addVar(lb=0, ub=hidros[h]["qmax"])
            s[h, t] = m.addVar(lb=0, ub=hidros[h]["vertimento_max"][t - 1])     # None = sem limite
            V[h, t + 1] = m.addVar(lb=hidros[h]["volume_min"], ub=hidros[h]["vmax"])

    deficit = {}
    for t in PERIODOS:
        deficit[t] = m.addVar(lb=0)


    # ===================================================================== 3. térmicas
    def partindo(i, t):
        """Soma de y nos últimos NUp períodos: vale 1 se a unidade está na trajetória de partida."""
        n_up = len(termicas[i]["trajetoria_partida"])
        return quicksum(y[i, t - k + 1] for k in range(1, n_up + 1) if t - k + 1 >= 1)


    def parando(i, t):
        """Soma de w nos próximos NDn períodos: vale 1 se a unidade está na trajetória de parada."""
        n_dn = len(termicas[i]["trajetoria_parada"])
        return quicksum(w[i, t + k] for k in range(1, n_dn + 1) if t + k <= T)


    def potencia_da_trajetoria(i, t):
        """Potência imposta pelas trajetórias: TrUp(k) quando a partida foi há k-1 períodos e
        TrDn(NDn-k+1) quando a parada será daqui a k períodos."""
        tr_up = termicas[i]["trajetoria_partida"]
        tr_dn = termicas[i]["trajetoria_parada"]
        n_dn = len(tr_dn)
        potencia = 0
        for k in range(1, len(tr_up) + 1):
            if t - k + 1 >= 1:
                potencia += tr_up[k - 1] * y[i, t - k + 1]
        for k in range(1, n_dn + 1):
            if t + k <= T:
                potencia += tr_dn[n_dn - k] * w[i, t + k]
        return potencia


    for i, ut in termicas.items():
        rampa = ajustes["rampa"] * (ut["pmax"] - ut["pmin"])
        ton = int(ut["ton_h"] / DT)              # tempos mínimos em períodos
        toff = int(ut["toff_h"] / DT)

        for t in PERIODOS:
            # (10.5 e 10.6) partida e parada a partir da mudança de status
            m.addCons(y[i, t] == w[i, t] + u[i, t] - u[i, t - 1])
            m.addCons(y[i, t] + w[i, t] <= 1)

            # (10.3) se houve partida nos últimos ton períodos, a unidade segue ligada.
            # Esta forma acumulada é equivalente à janela futura e gera uma
            # estrutura de unit commitment mais eficiente para o SCIP.
            inicio_ton = max(1, t - ton + 1)
            m.addCons(quicksum(y[i, k] for k in range(inicio_ton, t + 1)) <= u[i, t])

            # (10.4) se houve parada nos últimos toff períodos, a unidade segue desligada.
            inicio_toff = max(1, t - toff + 1)
            m.addCons(quicksum(w[i, k] for k in range(inicio_toff, t + 1)) <= 1 - u[i, t])

            # (10.8) e (10.9) entre Pmin e Pmax em operação normal; na trajetória, igual à curva
            normal = u[i, t] - partindo(i, t) - parando(i, t)
            m.addCons(gt[i, t] >= ut["pmin"] * normal + potencia_da_trajetoria(i, t))
            m.addCons(gt[i, t] <= ut["pmax"] * normal + potencia_da_trajetoria(i, t))

            # (10.17) e (10.18) rampas. A "chave" suspende o limite durante as trajetórias.
            # Na descida, a chave inclui w[i,t] para liberar a queda final até zero no período
            # da parada (decisão do usuário; sem isso nenhuma parada é viável).
            chave = partindo(i, t) + parando(i, t)
            folga = ut["pmax"] - rampa
            m.addCons(gt[i, t] - gt[i, t - 1] <= rampa + folga * chave)
            m.addCons(gt[i, t - 1] - gt[i, t] <= rampa + folga * (chave + w[i, t]))

        # a parada só pode ocorrer depois que a trajetória de parada inteira cabe no horizonte
        for t in range(1, len(ut["trajetoria_parada"]) + 1):
            m.addCons(w[i, t] == 0)

    # ===================================================================== 4. hidrelétricas
    furnas = hidros["FURNAS"]
    moraes = hidros["MORAES"]
    for t in PERIODOS:
        # balanço hídrico: volume seguinte = atual + 0,0018 x (afluência - turbinada - vertida)
        m.addCons(V["FURNAS", t + 1] == V["FURNAS", t] + HM3 * (furnas["afluencia"][t - 1] - q["FURNAS", t] - s["FURNAS", t]))
        # Moraes recebe também tudo o que Furnas solta no mesmo período
        m.addCons(V["MORAES", t + 1] == V["MORAES", t] + HM3 * (moraes["afluencia"][t - 1] + q["FURNAS", t] + s["FURNAS", t] - q["MORAES", t] - s["MORAES", t]))

    for h, uh in hidros.items():
        for t in PERIODOS:
            # limites de defluência (turbinada + vertida) do operuh.dat
            m.addCons(q[h, t] + s[h, t] >= uh["defluencia_min"][t - 1])
            if uh["defluencia_max"][t - 1] is not None:
                m.addCons(q[h, t] + s[h, t] <= uh["defluencia_max"][t - 1])
        # volume final >= inicial (fica no lugar do corte do DECOMP)
        m.addCons(V[h, T + 1] >= uh["v0"])

    # ===================================================================== 5. demanda e objetivo
    atendimento = {}
    for t in PERIODOS:
        geracao_termica = quicksum(gt[i, t] for i in termicas)
        geracao_hidraulica = quicksum(hidros[h]["rho"] * q[h, t] for h in hidros)
        atendimento[t] = m.addCons(geracao_termica + geracao_hidraulica + deficit[t] == demanda[t - 1])

    custo_termico = quicksum(DT * termicas[i]["cvu"] * gt[i, t] for i in termicas for t in PERIODOS)
    custo_vertimento = quicksum(ajustes["custo_vertimento"] * HM3 * s[h, t] for h in hidros for t in PERIODOS)
    custo_deficit = quicksum(DT * dados["custo_deficit"] * deficit[t] for t in PERIODOS)
    m.setObjective(custo_termico + custo_vertimento + custo_deficit, "minimize")

    # ===================================================================== 6. solução
    m.setParam("limits/gap", 1e-5)
    m.setParam("limits/time", 900)
    # As janelas longas de Ton/Toff geram muitas cliques. O presolve padrão
    # repete mais de cem rodadas neste caso, embora a solução feche no nó raiz.
    m.setParam("presolving/maxrounds", 10)
    if not salvar:
        m.hideOutput()
    m.optimize()
    status_milp = m.getStatus()
    custo_milp = m.getObjVal()
    gap_milp = m.getGap()
    print(f"\nMILP: {status_milp}, custo R$ {custo_milp:,.2f}, gap {gap_milp:.2e}")

    # Guarda a solução agora: o cálculo do CMO, a seguir, altera o modelo.
    resultado = pd.DataFrame()
    resultado["t"] = list(PERIODOS)
    resultado["inicio"] = [f"{dados['inicio'] + timedelta(hours=DT * (t - 1)):%Y-%m-%d %H:%M}" for t in PERIODOS]
    resultado["demanda"] = demanda
    for i in termicas:
        resultado[f"gt_{i}"] = [m.getVal(gt[i, t]) for t in PERIODOS]
        resultado[f"u_{i}"] = [round(m.getVal(u[i, t])) for t in PERIODOS]
    for h in hidros:
        resultado[f"q_{h}"] = [m.getVal(q[h, t]) for t in PERIODOS]
        resultado[f"s_{h}"] = [m.getVal(s[h, t]) for t in PERIODOS]
        resultado[f"gh_{h}"] = hidros[h]["rho"] * resultado[f"q_{h}"]
        resultado[f"V_{h}"] = [m.getVal(V[h, t + 1]) for t in PERIODOS]     # volume no fim do período
    resultado["deficit"] = [m.getVal(deficit[t]) for t in PERIODOS]

    compromisso = []        # (variável, valor) de u, y e w na solução inteira
    for i in termicas:
        for t in PERIODOS:
            for variavel in (u[i, t], y[i, t], w[i, t]):
                compromisso.append((variavel, round(m.getVal(variavel))))

    # ===================================================================== 7. CMO
    # O MILP não tem dual. Fixa-se o compromisso (u, y, w) e resolve-se de novo como LP;
    # o dual da restrição de atendimento, dividido por DT, é o CMO em R$/MWh.
    m.freeTransform()                            # volta o modelo ao estado editável
    for variavel, valor in compromisso:
        m.chgVarType(variavel, "C")
        m.chgVarLb(variavel, valor)
        m.chgVarUb(variavel, valor)
    m.setParam("limits/gap", 0)
    m.setParam("lp/disablecutoff", 1)            # resolve o LP até o fim, mesmo já conhecendo a solução do MILP
    m.setPresolve(SCIP_PARAMSETTING.OFF)         # sem pré-solução, os duais valem para as restrições originais
    m.setHeuristics(SCIP_PARAMSETTING.OFF)
    m.disablePropagation()
    m.hideOutput()
    m.optimize()
    print(f"LP com compromisso fixo: {m.getStatus()}, custo R$ {m.getObjVal():,.2f}")
    resultado["cmo"] = [m.getDualsolLinear(atendimento[t]) / DT for t in PERIODOS]

    # ===================================================================== 8. saída
    if salvar:
        pasta = Path(__file__).parent / "saida"
        pasta.mkdir(exist_ok=True)
        resultado.round(4).to_csv(pasta / "despacho.csv", sep=";", decimal=",", index=False)
        print(f"Resultados salvos em {pasta / 'despacho.csv'}")
    return {
        "resultado": resultado,
        "status": str(status_milp),
        "custo": custo_milp,
        "gap": gap_milp,
        "status_lp": str(m.getStatus()),
    }



if __name__ == "__main__":
    executar_despacho(salvar=True)
