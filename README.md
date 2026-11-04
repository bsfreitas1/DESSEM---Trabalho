# Despacho hidrotérmico com interface web

Aplicação local para leitura de um deck DESSEM, solução de um despacho hidrotérmico reduzido e análise interativa dos resultados.

## Requisitos

- Python 3;
- `pandas`;
- `pyscipopt` e solver SCIP;
- cópia local da PySDDP em `PySDDP-master`.

## Execução

Na pasta do projeto, execute:

```powershell
python server.py
```

Abra [http://127.0.0.1:8001](http://127.0.0.1:8001) no navegador.

Para executar somente o modelo e gerar `saida/despacho.csv`:

```powershell
python despacho.py
```

## Estrutura

- `leitura_pysddp.py`: lê e adapta os dados do deck com a PySDDP;
- `despacho.py`: monta e resolve o modelo com PySCIPOpt;
- `server.py`: fornece a interface e a API local;
- `index.html`, `app.js`, `styles.css` e `chart.css`: interface web.

São utilizados `entdados.dat`, `termdat.dat`, `operut.dat`, `rampas.dat`, `hidr.dat`, `dadvaz.dat` e `operuh.dat`. O `rampas.dat` fornece as trajetórias de acionamento e desligamento das termelétricas.

## Modelo

O problema representa duas hidrelétricas em cascata e duas termelétricas selecionáveis, em períodos de meia hora. A função objetivo minimiza:

- custo de geração térmica;
- penalidade por déficit;
- penalidade por vertimento.

As principais restrições incluem atendimento à demanda, balanço hídrico, limites operativos, tempos mínimos ligada/desligada, rampas de operação normal e trajetórias térmicas de partida e parada. Após o MILP, o compromisso térmico é fixado e o modelo é resolvido como LP para calcular o CMO.

## Interface

A página permite selecionar termelétricas, ajustar demanda, afluências, CVU, Ton, Toff, fração de rampa e custos. Cada alteração pode executar um novo cenário sem modificar o deck original.

Os resultados incluem indicadores, tabela e gráficos de geração, demanda, CMO, volumes, vazões, vertimentos, déficit e trajetórias térmicas. Também estão disponíveis filtros de período, seleção de curvas, zoom, tela cheia e exportação CSV.

O servidor mantém até 12 resultados recentes em memória e executa uma otimização por vez.
