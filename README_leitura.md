# Leitura dos dados do despacho

O módulo `leitura_pysddp.py` usa a cópia local da biblioteca PySDDP em `PySDDP-master` para ler os arquivos do deck DESSEM. A função `ler_dados()` converte os registros da biblioteca em listas e dicionários consumidos por `despacho.py`.

| Arquivo | Leitor PySDDP | Dados usados |
|---|---|---|
| `entdados.dat` | `Dadger` | horizonte, demanda, custo de déficit e volume inicial |
| `termdat.dat` | `CadTerm` | limites e tempos das térmicas |
| `operut.dat` | `Operut` | estado inicial, geração inicial e custo variável |
| `rampas.dat` | `Rampas` | trajetórias de partida e parada |
| `hidr.dat` | `Hidr` | cadastro físico das hidrelétricas |
| `dadvaz.dat` | `DadVaz` | data inicial e vazões diárias |
| `operuh.dat` | `Operuh` | limites operativos das hidrelétricas |

O `hidr.dat` deste deck tem registros de 832 bytes. Esse tamanho é informado explicitamente ao leitor da PySDDP. As listas por período têm 336 valores, com a posição zero correspondente a 31/10/2026 00:00.

Para conferir a leitura, execute `python leitura_pysddp.py`. Para resolver o problema, execute `python despacho.py` com as dependências da PySDDP e o PySCIPOpt instalados.
