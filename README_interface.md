# Interface local do despacho

Execute na pasta do projeto:

```powershell
python server.py
```

Abra http://127.0.0.1:8001 no navegador. O servidor usa apenas a interface local (`127.0.0.1`) e a biblioteca padrão do Python; a otimização requer `pyscipopt`, `pandas` e as dependências da cópia local da PySDDP.

A página mostra o custo total, as energias hidráulica e térmica, o CMO médio, a operação de cada meia hora, gráficos de geração, CMO, volumes, vazões e vertimentos, além de uma tabela diária e exportação CSV. As caixas abaixo do gráfico controlam as curvas visíveis, o seletor **Período** alterna entre todo o horizonte e uma meia hora específica, e o botão **Tela cheia** expande o painel sem distorcer o desenho. A aba **Recolher parâmetros** libera mais espaço horizontal para os resultados.

Os doze controles partem dos valores atuais do deck e são separados por sistema, hidrelétrica, termelétrica e premissas. Eles abrangem demanda, afluências de Furnas e Moraes, CVU, Ton e Toff de Angra 1 e Baixada, custo de déficit, fração de rampa e custo de vertimento. Ton e Toff são informados em horas, com passo de meia hora. Ao alterar um controle, a página espera 850 ms e envia o cenário para uma nova execução do mesmo MILP. O botão **Restaurar padrão** recupera os valores atuais. Os ajustes são aplicados em memória e não modificam o deck nem `saida/despacho.csv`. Use **Executar otimização** para iniciar manualmente quando o recálculo automático estiver desativado.

A API local expõe `GET /api/config` e `POST /api/dispatch`. Uma otimização é executada por vez, e até 12 cenários recentes ficam em cache na memória. O tempo limite do solver continua sendo 900 segundos, conforme `despacho.py`.

## Desempenho

No caso base, o presolve padrão do SCIP executava 121 rodadas e consumia a maior parte do tempo, devido às janelas binárias longas de Ton e Toff. O modelo fechava o gap no nó raiz. As restrições de tempo mínimo foram reescritas na forma acumulada equivalente de compromisso térmico, e o presolve foi limitado a 10 rodadas. O tempo medido caiu de 15,31 s para 4,66 s, preservando o status ótimo, o custo de R$ 8.534.369,26, o compromisso das térmicas e o gap zero. Como há múltiplos despachos hidráulicos ótimos, vazões e gerações hidráulicas podem assumir outra solução com o mesmo custo. O servidor também reutiliza em memória os dados já lidos pela PySDDP, evitando reabrir todo o deck em cada cenário.
