"""Gráficos do despacho, a partir de saida/despacho.csv (gerado por despacho.py).

Painéis: geração x demanda, volume de Furnas, volume de Moraes, geração térmica e CMO.
"""
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

PASTA = Path(__file__).parent / "saida"
COR = {"ANGRA1": "#2a78d6", "BAIXADA": "#eb6834", "FURNAS": "#1baf7a", "MORAES": "#eda100",
       "DEFICIT": "#e87ba4", "CMO": "#6250d6"}

resultado = pd.read_csv(PASTA / "despacho.csv", sep=";", decimal=",", parse_dates=["inicio"])
tempo = resultado["inicio"]

fig, paineis = plt.subplots(5, 1, figsize=(12, 15), sharex=True)

# ===================================================================== 1. geração x demanda
painel = paineis[0]
painel.stackplot(tempo,
                 resultado["gt_ANGRA1"], resultado["gt_BAIXADA"],
                 resultado["gh_FURNAS"], resultado["gh_MORAES"], resultado["deficit"],
                 labels=["Angra 1", "Baixada", "Furnas", "M. de Moraes", "Déficit"],
                 colors=[COR["ANGRA1"], COR["BAIXADA"], COR["FURNAS"], COR["MORAES"], COR["DEFICIT"]],
                 step="post")
painel.step(tempo, resultado["demanda"], where="post", color="black", linewidth=1.5, label="Demanda")
painel.set_title("Geração e demanda (MW)")
painel.set_ylim(0, 1.25 * resultado["demanda"].max())      # espaço para a legenda
painel.legend(loc="upper left", ncol=6)

# ===================================================================== 2 e 3. volumes
paineis[1].plot(tempo, resultado["V_FURNAS"], color=COR["FURNAS"], linewidth=2)
paineis[1].set_title("Furnas: volume no fim do período (hm³)")

paineis[2].plot(tempo, resultado["V_MORAES"], color=COR["MORAES"], linewidth=2)
paineis[2].set_title("M. de Moraes: volume no fim do período (hm³)")

# ===================================================================== 4. térmicas
painel = paineis[3]
painel.step(tempo, resultado["gt_ANGRA1"], where="post", color=COR["ANGRA1"], linewidth=2, label="Angra 1")
painel.step(tempo, resultado["gt_BAIXADA"], where="post", color=COR["BAIXADA"], linewidth=2, label="Baixada")
painel.set_title("Geração térmica (MW); zero = desligada")
painel.legend(loc="lower right")

# ===================================================================== 5. CMO
painel = paineis[4]
painel.step(tempo, resultado["cmo"], where="post", color=COR["CMO"], linewidth=2)
painel.set_yscale("log")                                    # o custo de déficit é ~250 vezes o CVU de Angra
painel.set_title("CMO (R$/MWh, escala log)")

# ===================================================================== acabamento
for painel in paineis:
    painel.grid(color="#e1e0d9", linewidth=0.6)
    painel.set_axisbelow(True)
paineis[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
fig.tight_layout()
fig.savefig(PASTA / "graficos.png", dpi=120)
print(f"Gráficos salvos em {PASTA / 'graficos.png'}")
