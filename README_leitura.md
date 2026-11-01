# leitura.py: guia de leitura

O `leitura.py` lê o deck DESSEM D31 e devolve os dados em listas e dicionários simples, prontos para o `despacho.py`. Ele não monta modelo nem aplica premissas. A escala da demanda (K), a rampa de 20% e o custo de vertimento ficam no `despacho.py`.

Para conferir os dados lidos: `python leitura.py`.

Os números de linha se referem à versão de 01/11/2026. Se o código mudar, confira antes de usar.

**Convenções:**

- **Colunas:** contadas a partir de 1, como no Manual do Usuário do DESSEM. Dá para comparar cada `campo(linha, a, b)` com o leiaute do manual.
- **Listas por período:** têm 336 valores, e a **posição 0** é a meia hora 31/10 00:00. No `despacho.py`, o período t corresponde à posição t − 1.

**Arquivos do deck usados:**

| Arquivo | Registro | O que fornece |
|---|---|---|
| `entdados.dat` | TM | dias do estudo e duração dos intervalos |
| `entdados.dat` | DP | demanda do Sudeste (subsistema 1) |
| `entdados.dat` | CD | custo de déficit |
| `entdados.dat` | UH | volume inicial das hidrelétricas (% do útil) |
| `termdat.dat` | CADUNIDT | Pmax, Pmin, tempos mínimos ligada e desligada |
| `operut.dat` | INIT, OPER | estado inicial e CVU |
| `rampas.dat` | RAMP | trajetórias de partida e parada |
| `hidr.dat` (binário) | registro da usina | volumes, polinômio cota × volume, máquinas, produtibilidade, canal de fuga |
| `dadvaz.dat` | vazões diárias | afluências incrementais |
| `operuh.dat` | LIM | limites de defluência, vertimento e cota |

---

## Linhas 1–20: cabeçalho e constantes

- **9:** `struct` lê números do arquivo binário `hidr.dat`.
- **10:** `datetime` monta a data de início do estudo.
- **11:** `Path` monta caminhos de pasta.
- **13:** `PASTA_DECK` é a pasta do deck, ao lado do script.
- **16:** `TERMICAS` associa cada nome a (número da usina, unidade equivalente):
  - **Angra 1:** usina 1, unidade 1 (tem uma só unidade).
  - **Baixada Fluminense:** usina 211, unidade 3. A Baixada é ciclo combinado: no `termdat.dat` há três configurações equivalentes, e o registro CADCONF diz quais unidades reais formam cada uma. A 3 reúne as três unidades reais (ciclo completo, 530 MW); a 1 e a 2 são configurações parciais de 265 MW. A diretriz usa só a 3.
- **17:** `HIDRELETRICAS`: Furnas é a usina 6 e Moraes, a 7.
- **18:** `MONTANTE_FURNAS = [1, 2, 4]`: Camargos, Itutinga e Funil-Grande. Pelo campo de jusante do `hidr.dat`, a cadeia é Camargos → Itutinga → Funil-Grande → Furnas → Moraes → Estreito, e nenhuma outra usina deságua nela.
- **20:** 48 meias horas por dia.

---

## Linhas 23–74: funções auxiliares

### `ler_linhas` (24–26)

Lê um arquivo de texto do deck e devolve a lista de linhas. Usa a codificação `latin-1`, em que cada byte vira exatamente um caractere. Assim as colunas ficam alinhadas como no formato Fortran original, mesmo com acentos em UTF-8 nos comentários de alguns arquivos.

### `campo` (29–31)

Devolve o texto entre duas colunas, contadas a partir de 1 e inclusivas, como no manual. Em Python, `linha[coluna_inicial - 1:coluna_final]` dá exatamente esse trecho, e o `.strip()` tira os espaços.

Exemplo, na linha `TM  31    0   0      0.5     0     LEVE`:

- `campo(linha, 5, 6)` = `"31"` (o dia);
- `campo(linha, 20, 24)` = `"0.5"` (a duração).

### `encontrar_linha` (34–38)

Devolve a posição da primeira linha que começa com um texto dado. É usada no `dadvaz.dat` para achar o cabeçalho de data e o início das vazões.

### `registros_do_bloco` (41–52)

Devolve as linhas entre o cabeçalho de um bloco e o `FIM` seguinte, sem comentários (linhas com `&`) nem linhas vazias. É usada para os blocos `INIT` e `OPER` do `operut.dat` e `RAMP` do `rampas.dat`.

É necessária porque, no `operut.dat`, as linhas do INIT e do OPER começam igualmente pelo número da usina. Só pela posição no arquivo se sabe a qual bloco cada uma pertence.

### `periodo` (55–57)

Converte (dia, hora, meia hora) na posição de 0 a 335:

```
posição = (índice do dia na lista de dias) × 48 + hora × 2 + meia hora
```

Exemplo: dia 1 (o 2º dia do estudo, índice 1), 18h, meia hora 0 → 1 × 48 + 36 + 0 = **84**, que é a meia hora de 01/11 às 18:00.

### `cota` (60–62)

Calcula a cota de montante (m) pelo polinômio cota × volume do `hidr.dat`: a0 + a1·V + a2·V² + a3·V³ + a4·V⁴. Exemplo: Furnas no volume inicial (15.923,7 hm³) está na cota de 763,07 m.

### `volume_da_cota` (65–74)

Faz o caminho inverso: acha o volume em que a cota vale um valor desejado, por **bisseção**.

- Começa com o intervalo [vmin, vmax].
- A cada passo, olha o ponto do meio: se a cota ali está abaixo da desejada, a resposta está na metade de cima; senão, na de baixo.
- Depois de 100 divisões, o intervalo fica minúsculo.

É usada para Moraes: a cota mínima de 655,3 m vira o volume mínimo de **1.906,5 hm³**.

---

## Linhas 77–124: entdados.dat

### Como o deck discretiza o tempo (registro TM)

Cada registro TM descreve um intervalo do estudo. Os do dia 01, por exemplo:

```
TM  01    0   0        1     0    MEDIA
TM  01    1   0       17     0     LEVE
TM  01   18   0        6     0    MEDIA
```

Os campos são: dia, hora de início, meia hora (0 = hora cheia, 1 = :30), duração em horas, flag de rede e nome do patamar. A primeira linha quer dizer: **no dia 01, um intervalo que começa às 00:00 e dura 1 hora, classificado como patamar médio**.

O deck D31 só tem resolução de meia hora no primeiro dia. Do dia 01 em diante, a carga vem em blocos de duração variável, os patamares:

| Dia | Discretização no deck |
|---|---|
| 31/10 (sábado) | 48 meias horas, cada uma com sua demanda |
| 01/11 (domingo) | 3 blocos: 00h por 1 h (média), 01h por 17 h (leve), 18h por 6 h (média) |
| 02/11 (segunda, Finados) | os mesmos 3 blocos de domingo |
| 03 a 06/11 (terça a sexta) | 5 blocos: 00h por 2 h (média), 02h por 6 h (leve), 08h por 8 h (média), 16h por 6 h (pesada), 22h por 2 h (média) |

São 74 intervalos no total (48 + 2×3 + 4×5). É o padrão do DESSEM: detalha o primeiro dia e agrega o restante da semana em patamares, para reduzir o tamanho do problema. O feriado de Finados aparece com a mesma estrutura de domingo, sem patamar pesado.

O nome do patamar (leve, média, pesada) é só uma classificação do nível de carga daquele trecho do dia; não altera a duração nem o valor da demanda. Os blocos seguem o perfil típico de cada tipo de dia:

- **Domingo e feriado:** 00–01h ainda é o fim da carga da noite anterior (média); 01–18h é carga baixa o dia todo (leve); 18–24h é a subida da noite (média).
- **Dias úteis:** 00–02h média; 02–08h madrugada (leve); 08–16h horário comercial (média); 16–22h ponta (pesada); 22–24h média.

O modelo usa meia hora uniforme nos 336 períodos (como pede a diretriz) e repete o valor de cada bloco em todas as meias horas dele. Por isso a demanda aparece em degraus a partir de 01/11. A grade de meia hora continua necessária nesses dias, porque partidas, paradas, rampas e tempos mínimos das térmicas são definidos em meias horas.

### `ler_horizonte` (78–88)

Percorre os registros TM:

- **84–86:** guarda os dias na ordem em que aparecem: [31, 1, 2, 3, 4, 5, 6]. Essa lista é usada pela função `periodo`.
- **87:** soma as durações (colunas 20–24): 48 × 0,5 + 24 × 6 = 168 h.
- **88:** devolve os dias e o número de meias horas: 168 × 2 = **336**.

### `ler_demanda` (91–108)

Lê o registro DP do subsistema 1 (Sudeste), em MW.

| Colunas | Campo |
|---|---|
| 5–6 | subsistema |
| 9–10 | dia |
| 12–13 | hora |
| 15 | meia hora |
| 25–34 | demanda (MW) |

- **94–100, primeiro laço:** monta um dicionário posição → valor, só com as posições onde algum registro DP começa.
- **102–107, segundo laço:** percorre as 336 posições e "arrasta" o valor: **cada registro vale do seu início até o início do próximo**. No dia 31 há um registro por meia hora; nos outros dias, um por patamar.

Exemplo, dia 01:

| Registro DP | Posições | Demanda do SE | No modelo (× 0,04533, aplicado no `despacho.py`) |
|---|---|---|---|
| 01, 00h | 48–49 (00:00–01:00) | 41.006 MW | 1.858,8 MW |
| 01, 01h | 50–83 (01:00–18:00) | 39.096 MW | 1.772,2 MW |
| 01, 18h | 84–95 (18:00–24:00) | 45.545 MW | 2.064,6 MW |

A demanda do SE vai de 37.858 a 53.668 MW. Depois da escala K, fica entre 1.716 e 2.433 MW.

### `ler_custo_deficit` (111–115)

Registro CD do subsistema 1: subsistema nas colunas 4–5 e custo nas colunas 26–35. Resultado: **8.291,25 R$/MWh**. O deck tem um único patamar de déficit, valendo até 100% da demanda.

### `ler_volume_inicial` (118–124)

Registro UH: número da usina nas colunas 5–7 e volume inicial, em % do volume útil, nas colunas 30–39. Furnas começa com **64,6%** e Moraes com **77,54%**.

---

## Linhas 127–185: térmicas

### `ler_trajetoria` (128–148)

Lê do bloco RAMP do `rampas.dat` a potência em cada meia hora da partida (sentido `A`) ou da parada (sentido `D`).

| Colunas | Campo |
|---|---|
| 1–3 | usina |
| 5–7 | unidade |
| 18 | sentido: A = partida, D = parada |
| 21–30 | potência (MW) |
| 32–36 | tempo (horas) |
| 38 | meia hora (0 ou 1) |

- **133–137:** guarda cada ponto no dicionário `pontos` com o índice **k = 2 × Tempo + meia hora**. Exemplo, na partida de Angra:
  - a linha `1   1      S   A     122.000     0 1` é Tempo 0 com meia hora 1, ou seja, k = 1, valendo 122 MW;
  - a linha `… 520.000     5 0` é Tempo 5 com meia hora 0, ou seja, k = 10, valendo 520 MW.
- **139–140, só na parada:** o arquivo termina a curva de parada com um ponto de 0 MW. Esse ponto é a unidade já desligada, ou seja, o período do w. Ele sai da trajetória, que fica só com os pontos em que a unidade ainda está ligada.
- **142–147:** monta a lista de k = 1 até o último. Se um k não existe no arquivo, repete o valor anterior. É o caso do 2º ponto da partida da Baixada, que falta no arquivo e é preenchido com 15 MW.

Trajetórias lidas:

| Usina | Partida (MW por meia hora) | Parada (MW por meia hora) |
|---|---|---|
| Angra 1 | 122, 212, 302, 392, 482, 490, 499, 508, 517, 520 (10 pontos) | 517, 508, 499, 490, 482, 392, 302, 212, 122 (9 pontos) |
| Baixada | 15, 15*, 15, 25, 25, 40, 40, 130, 130, 220, 220, 255, 255, 275, 275, 285, 285, 300, 300, 320 (20 pontos) | 250, 100 (2 pontos) |

\* ponto ausente no arquivo, repete o anterior.

A partida termina em Pmin (520 e 320 MW); depois dela começa a operação normal.

### `ler_termicas` (151–185)

- **152–156:** lê o `termdat.dat`, os blocos INIT e OPER do `operut.dat` e o bloco RAMP do `rampas.dat`.
- **159–184:** para cada térmica, procura os registros da sua (usina, unidade).

**CADUNIDT, `termdat.dat` (162–169):**

| Colunas | Campo |
|---|---|
| 10–12 | usina |
| 14–15 | unidade |
| 34–43 | Pmax (MW) |
| 45–54 | Pmin (MW) |
| 56–60 | tempo mínimo ligada (h) |
| 62–66 | tempo mínimo desligada (h) |

**INIT, `operut.dat` (171–175):**

| Colunas | Campo |
|---|---|
| 1–3 | usina |
| 19–21 | unidade |
| 25–26 | status inicial (1 = ligada) |
| 30–39 | geração inicial (MW) |

**OPER, `operut.dat` (177–180):** usina nas colunas 1–3, unidade nas 18–19 e CVU (R$/MWh) nas 57–66.

**Trajetórias (182–183):** pela `ler_trajetoria`.

Valores lidos:

| Dado | Angra 1 | Baixada (unid. 3) |
|---|---|---|
| Pmax / Pmin (MW) | 640 / 520 | 530 / 320 |
| Tempo mínimo ligada / desligada (h) | 168 / 168 | 72 / 48 |
| CVU (R$/MWh) | 31,17 | 196,24 |
| Estado inicial | desligada, 0 MW | ligada, 510 MW |

**O que não é lido:**

- **Horas no estado inicial (INIT):** o histórico já cumpre os tempos mínimos (Angra desligada há 1.007,5 h ≥ 168; Baixada ligada há 227 h ≥ 72), então não há restrição residual no início.
- **Campos de rampa do CADUNIDT:** estão em branco no deck. A rampa de 20% de (Pmax − Pmin) é premissa, definida no `despacho.py`.
- **Registro UT do `entdados.dat` (limites declarados):** declara Angra 1 com 0/0 MW (indisponível no caso oficial) e a Baixada com 510/530 MW. Pela diretriz, os limites vêm do CADUNIDT e a manutenção fica fora do escopo.

---

## Linhas 188–308: hidrelétricas

### `ler_cadastro_hidr` (189–201)

O `hidr.dat` é binário: um registro de **832 bytes** por usina, na ordem do número da usina. O registro da usina N começa no byte (N − 1) × 832.

O `struct.unpack_from(formato, dados, posição)` lê números a partir de uma posição:

- `<` indica a ordem de bytes do arquivo (little-endian);
- `f` é número real de 4 bytes, `d` é real de 8 bytes e `i` é inteiro de 4 bytes;
- o número antes da letra é quantos valores ler (`5d` = 5 reais de 8 bytes).

| Byte | Formato | Campo | Furnas | Moraes |
|---|---|---|---|---|
| 40 | `<2f` | Vmin e Vmax (hm³) | 5.620,5 / 21.569,7 | 1.598,8 / 4.187,0 |
| 64 | `<5d` | polinômio cota × volume (a0 … a4) | | |
| 196 | `<5i` | número de máquinas de cada conjunto | 6, 2 | 2, 2, 4, 2 |
| 556 | `<5i` | vazão nominal por máquina em cada conjunto (m³/s) | 188, 189 | 111, 126, 131, 137 |
| 576 | `<f` | produtibilidade específica (MW/(m³/s)/m) | 0,008996 | 0,008657 |
| 732 | `<f` | canal de fuga médio, a cota de jusante (m) | 672,20 | 621,10 |

O registro tem 832 bytes, e não os 792 do leiaute clássico, porque aqui os dois polinômios (cota × volume e cota × área) estão gravados com 8 bytes por coeficiente. Isso desloca em 40 bytes todos os campos depois do byte 64.

### `ler_vazoes` (204–215)

Lê as vazões diárias do `dadvaz.dat`. A seção começa 3 linhas depois de `VAZOES DIARIAS` (o título e duas linhas de cabeçalho) e vai até o `FIM`.

| Colunas | Campo |
|---|---|
| 1–3 | usina |
| 25–26 | dia |
| 45–53 | vazão (m³/s) |

Monta um dicionário (usina, dia) → vazão. Todas as vazões usadas são do tipo 1 (incremental): a água que surge no trecho entre a usina de cima e a usina em questão.

### `vazao_por_dia` (218–226)

Devolve um valor por dia, na ordem da lista `dias`. **Dia sem registro repete o anterior**, porque no `dadvaz` cada registro vale até o próximo (convenção do DESSEM). Casos no deck:

- Camargos nos dias 02, 05 e 06;
- Moraes no dia 03;
- Itutinga, que só tem o dia 31 (0 m³/s) e repete o zero nos demais.

### `instante_operuh` (229–239)

Converte o campo de início ou de fim de um registro LIM do `operuh.dat` em posição:

- `I` é o início do estudo (posição 0);
- `F` é o fim (posição 336, que não entra na janela);
- nos demais casos, o dia está em (c, c+1), a hora em (c+3, c+4) e a meia hora em c+6, onde c é a coluna do dia: 21 para o início e 29 para o fim.

### `limite_operuh` (242–257)

Monta uma lista de 336 valores com o limite de uma restrição do `operuh.dat` em cada período (`None` = sem limite).

| Colunas do registro LIM | Campo |
|---|---|
| 15–19 | número da restrição |
| 21–27 | início (dia, hora, meia hora) |
| 29–35 | fim (dia, hora, meia hora) |
| 39–48 | limite inferior |
| 49–58 | limite superior |

Para cada registro LIM da restrição, se o lado pedido não estiver em branco, preenche as posições do início até antes do fim. Exemplo:

- a 11145 vai de `I` até `1 00 0` e preenche as posições 0–47 (dia 31) com 1.440;
- a 11394 vai de `1 00 0` até `F` e preenche as posições 48–335 com 1.440.

### `ler_hidreletricas` (260–308)

**Linhas 261–264:** lê o `hidr.dat`, o `operuh.dat`, os volumes iniciais (UH) e as vazões.

**Linha 268:** campos do cadastro (`ler_cadastro_hidr`).

**Linha 269, volume inicial:** v0 = Vmin + % útil × (Vmax − Vmin).

- Furnas: 5.620,5 + 0,646 × 15.949,1 = **15.923,7 hm³**
- Moraes: 1.598,8 + 0,7754 × 2.588,2 = **3.605,7 hm³**

**Linhas 272–274, engolimento máximo:** a soma de máquinas × vazão por máquina, conjunto a conjunto.

- Furnas: 6 × 188 + 2 × 189 = **1.506 m³/s**
- Moraes: 2 × 111 + 2 × 126 + 4 × 131 + 2 × 137 = **1.272 m³/s**

#### Linhas 276–278: produtibilidade

A produtibilidade é **constante**: um único valor por usina, calculado no volume inicial e usado no horizonte inteiro. No modelo, a geração hidráulica é **gh = ρ × q** (MW = MW/(m³/s) × m³/s).

```
ρ = produtibilidade específica × queda
queda = cota de montante no volume inicial − cota do canal de fuga
```

| Ingrediente | De onde vem | Furnas | Moraes |
|---|---|---|---|
| Produtibilidade específica (MW/(m³/s)/m) | `hidr.dat`, byte 576 | 0,008996 | 0,008657 |
| Volume inicial (hm³) | `entdados` UH, com Vmin e Vmax do `hidr.dat` | 15.923,7 | 3.605,7 |
| Cota de montante (m) | polinômio cota × volume (byte 64), no volume inicial | 763,07 | 663,89 |
| Cota do canal de fuga (m) | `hidr.dat`, byte 732 | 672,20 | 621,10 |
| **Queda (m)** | diferença das duas cotas | **90,87** | **42,79** |
| **ρ (MW por m³/s)** | específica × queda | **0,8174** | **0,3704** |

**O que é a produtibilidade específica:** é o rendimento do conjunto turbina-gerador expresso em MW por m³/s por metro de queda. A potência hidráulica é P = 9,81 × η × q × h / 1000 (em MW). Então 0,008996 corresponde a um rendimento η ≈ 92% em Furnas, e 0,008657 a η ≈ 88% em Moraes.

**Exemplo:** se Furnas turbinar 1.440 m³/s, gera 0,8174 × 1.440 ≈ 1.177 MW.

**Simplificações embutidas nesse ρ constante:**

1. **Queda fixa no volume inicial.** A cota de montante muda com o volume, mas aqui o efeito é desprezível: o volume de Furnas varia cerca de ±25 hm³ na semana, o que muda a cota em ±0,03 m de 91 m (0,03%). Em Moraes, a variação de uns 20 hm³ muda a cota em cerca de 0,08 m de 43 m (0,2%).
2. **Canal de fuga fixo.** Na realidade, o nível a jusante sobe quando a usina solta mais água, o que reduz a queda. O deck traz essas curvas no `polinjus.csv`, mas a diretriz mandou usar só o `hidr.dat`, que tem o valor médio.
3. **Sem perdas hidráulicas,** por decisão do usuário. Descontando as perdas do `hidr.dat` (0,80 m em Furnas e 1,14 m em Moraes), ρ cairia 0,9% e 2,7%: 0,8102 e 0,3605.
4. **Rendimento constante.** Na realidade, ele depende de quanto cada máquina está carregada. O DESSEM oficial usa a FPHA (função de produção hidrelétrica aproximada), uma função linear por partes da vazão turbinada, do volume e do vertimento. Aqui é uma reta pela origem.
5. **Usina como um bloco único.** Não há máquinas individuais: a turbinada vai continuamente de 0 ao engolimento total, respeitando apenas a defluência mínima.

Neste estudo, as simplificações 1 e 2 pesam pouco, porque os volumes quase não variam. As de maior efeito potencial são a 4 e a 5. Mesmo assim, para uma semana com reservatórios estáveis, o ρ constante é uma aproximação razoável.

#### Linhas 284–292: afluências

```python
afluencia_furnas = vazao_por_dia(vazoes, 6, dias)              # 286: incremental de Furnas
for usina in MONTANTE_FURNAS:                                  # 287: para cada usina de cima (1, 2, 4)
    montante = vazao_por_dia(vazoes, usina, dias)              # 288: incremental dela, dia a dia
    afluencia_furnas = [a + b for a, b in zip(afluencia_furnas, montante)]   # 289: soma dia a dia
```

- **286:** começa com a incremental de Furnas, uma lista de 7 valores (um por dia): [758, 792, 801, …].
- **287:** percorre as usinas de montante (`MONTANTE_FURNAS`, linha 18).
- **288:** lê a incremental diária da usina da vez.
- **289:** soma as duas listas posição a posição, ou seja, dia com dia. O `zip` emparelha os valores do mesmo dia: (758, 101), (792, 106), … e cada par vira uma soma.
- **290:** Moraes recebe só a incremental própria. A água de Furnas entra pelo balanço hídrico, no `despacho.py` (o q + s de Furnas no balanço de Moraes).
- **291–292:** transformam os 7 valores diários em 336 meias horas. `t // 48` dá o dia de cada período, e o mesmo valor se repete 48 vezes.

A premissa é que as usinas de montante não guardam água: deixam passar o que recebem.

| m³/s | 31/10 | 01/11 | 02/11 | 03/11 | 04/11 | 05/11 | 06/11 |
|---|---|---|---|---|---|---|---|
| Furnas (incremental) | 758 | 792 | 801 | 782 | 751 | 721 | 697 |
| Funil-Grande | 231 | 216 | 191 | 201 | 227 | 212 | 191 |
| Itutinga | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Camargos | 101 | 106 | 106* | 107 | 108 | 108* | 108* |
| **Afluência de Furnas** | **1.090** | **1.114** | **1.098** | **1.090** | **1.086** | **1.041** | **996** |
| **Afluência de Moraes** | **146** | **141** | **139** | **139*** | **135** | **128** | **125** |

\* dia sem registro, repete o anterior.

**O que acontece com essa água na solução:** toda a água que entra é turbinada, e nada é vertido.

| | Afluência média | Turbinada média | Vertimento | Geração média |
|---|---|---|---|---|
| Furnas | 1.073,6 m³/s | 1.073,6 m³/s | 0 | ≈ 878 MW |
| Moraes | 1.209,7 m³/s (136 próprios + 1.073,6 de Furnas) | 1.209,7 m³/s | 0 | ≈ 448 MW |

Como o volume final não pode ficar abaixo do inicial, a energia hidráulica da semana fica fixada pelas afluências: cerca de 1.326 MW em média, uns 63% da demanda. O otimizador só escolhe **quando** turbinar, usando o reservatório para deslocar água no tempo.

**Simplificações:**

1. **Tempo de viagem ignorado.** O deck tem esse dado: o registro `TVIAG` do `entdados.dat` diz que a água leva **6 horas** de Furnas até Moraes (e 12 h de Itutinga a Funil-Grande, 23 h de Funil-Grande a Furnas). O modelo considera que ela chega na mesma meia hora, como pede a diretriz.
   - Com tempo de viagem, Moraes receberia em t o que Furnas soltou 12 períodos antes.
   - Nas primeiras 6 horas, Moraes receberia a água solta antes do início do estudo. Esse dado está no `deflant.dat`, que não é usado.
   - O efeito é pequeno, porque Moraes tem reservatório para absorver o atraso.
2. **Usinas de montante sem regularização:** Camargos tem reservatório e, na realidade, poderia guardar ou soltar água.
3. **Afluência constante ao longo do dia:** é a resolução do `dadvaz`.
4. **Sem evaporação e sem retiradas de água:** o `hidr.dat` tem coeficientes de evaporação, mas eles não são usados.

#### Linhas 294–307: restrições operativas do operuh.dat

| Linhas | Restrição | Usina | O que limita | Valor no modelo |
|---|---|---|---|---|
| 295 | 00443 | Furnas | defluência (q + s) mínima | ≥ 131 m³/s |
| 296–298 | 11145 e 11394 | Furnas | defluência máxima | ≤ 1.440 m³/s |
| 299 | 10186 | Furnas | vertimento | = 0 (proibido verter) |
| 300 | | Furnas | volume mínimo | o do cadastro, 5.620,5 hm³ |
| 302 | 00445 | Moraes | defluência mínima | ≥ 149 m³/s |
| 303–304 | | Moraes | defluência e vertimento máximos | sem limite (`None`) |
| 305–307 | 00444 | Moraes | cota mínima de 655,3 m | volume ≥ 1.906,5 hm³ |

- **Linha 298:** junta as duas restrições de defluência máxima de Furnas. Em cada período, usa a 11145 se ela estiver definida (até 01/11 00h) e a 11394 nos demais (de 01/11 em diante). As duas têm a mesma flag `D` no registro REST e foram tratadas como ativas.
- **Linhas 305–307:** a cota mínima de Moraes é convertida em volume pela bisseção (`volume_da_cota`). O volume mínimo usado no modelo é o maior entre esse valor (1.906,5) e o Vmin do cadastro (1.598,8).
- **Não lidas:** as restrições 00296 (Furnas ≤ 4.000 m³/s) e 00300 (Moraes ≤ 4.400 m³/s), dominadas pelos outros limites.

---

## Linhas 311–331: tudo junto

### `ler_data_inicio` (312–317)

Lê a data de início no cabeçalho do `dadvaz.dat`. Duas linhas abaixo de `Hr  Dd  Mm  Ano` está `00  31  10  2026`, que vira 31/10/2026 às 00:00.

### `ler_dados` (320–331)

É a função que o `despacho.py` chama. Devolve um dicionário:

| Chave | Conteúdo |
|---|---|
| `inicio` | data e hora de início (31/10/2026 00:00) |
| `dias` | [31, 1, 2, 3, 4, 5, 6] |
| `T` | 336 |
| `demanda_se` | lista de 336 valores de demanda do SE, em MW, ainda sem a escala K |
| `custo_deficit` | 8.291,25 R$/MWh |
| `termicas` | por usina: `pmax`, `pmin`, `ton_h`, `toff_h`, `ligada_inicio`, `geracao_inicio`, `cvu`, `trajetoria_partida`, `trajetoria_parada` |
| `hidreletricas` | por usina: campos do cadastro (`vmin`, `vmax`, `polinomio_cota`, `maquinas`, `vazao_maquina`, `prod_especifica`, `canal_fuga`), além de `v0`, `qmax`, `rho`, `volume_min` e das listas de 336 valores `afluencia`, `defluencia_min`, `defluencia_max` e `vertimento_max` |

---

## Linhas 334–344: conferência

O bloco `if __name__ == "__main__":` só roda quando o arquivo é executado diretamente (`python leitura.py`), e não quando é importado pelo `despacho.py`. Ele imprime a data de início, os dias, a faixa da demanda, o custo de déficit, os dados das térmicas e os principais dados das hidrelétricas, para conferir a leitura.
