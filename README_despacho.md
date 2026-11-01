# despacho.py: guia de leitura

O `despacho.py` monta e resolve o despacho hidrotérmico reduzido a partir do deck DESSEM D31:

- **Usinas:** Angra 1 e Baixada Fluminense (térmicas); Furnas → Mascarenhas de Moraes (hidrelétricas em cascata).
- **Sistema e horizonte:** barra única, 336 meias horas (31/10 a 06/11/2026).
- **Formulação:** equações da seção 10 do Manual de Metodologia do DESSEM.

Para rodar: `python despacho.py` (gera `saida/despacho.csv`) e depois `python graficos.py`.

Os números de linha se referem à versão de 01/11/2026. Se o código mudar, confira antes de usar.

**Resultado do caso base:** custo de R$ 8.534.369,26, gap 0 (ótimo comprovado), sem déficit, CMO de 31,17 R$/MWh em todos os períodos.

---

## Linhas 1–20: cabeçalho e importações

- **1–13:** o texto entre aspas triplas é só a descrição do arquivo; o Python não executa nada ali.
- **14:** `timedelta` serve para somar horas a uma data. É usado no fim para escrever a hora de cada período (31/10 00:00 + 0,5 h × (t−1)).
- **15:** `Path` monta caminhos de pasta (a pasta `saida`).
- **17:** `pandas` monta a tabela de resultados e grava o CSV.
- **18:** do PySCIPOpt vêm três coisas:
  - `Model`: o problema de otimização;
  - `quicksum`: soma de expressões, mais rápida que o `sum` comum;
  - `SCIP_PARAMSETTING`: atalho para desligar módulos do solver, usado no cálculo do CMO.
- **20:** a função que lê o deck, definida em `leitura.py`.

## Linhas 22–27: premissas (o que não vem do deck)

| Linha | Valor | Significado |
|---|---|---|
| 23 | `DT = 0.5` | cada período dura meia hora |
| 24 | `HM3 = 0,0018` | 1 m³/s durante meia hora = 1 × 1800 s = 1800 m³ = 0,0018 hm³; converte vazão em volume no balanço hídrico |
| 25 | `K_DEMANDA = 0,04533` | reduz a demanda do Sudeste (38 a 54 mil MW) para a escala das 4 usinas (1.716 a 2.433 MW) |
| 26 | `FRACAO_RAMPA = 0,20` | rampa = 20% de (Pmax − Pmin): 24 MW em Angra, 42 MW na Baixada |
| 27 | `CUSTO_VERTIMENTO = 0,2` | penalidade de 0,2 R$ por hm³ vertido |

## Linhas 30–38: dados

- **31:** `ler_dados()` devolve um dicionário com tudo o que foi lido do deck: data de início, dias, `T`, demanda do SE, custo de déficit, térmicas e hidrelétricas.
- **32:** `T = 336` meias horas.
- **33:** `range(1, T + 1)` gera 1, 2, …, 336 (o `range` não inclui o último número). Os períodos começam em 1 para bater com a notação do manual.
- **34–35:** atalhos: `termicas["BAIXADA"]["pmin"]` em vez de `dados["termicas"]["BAIXADA"]["pmin"]`.
- **36:** multiplica cada valor de demanda do SE por K.
  - **Detalhe que aparece no código todo:** listas em Python começam na posição 0. Então a demanda do período t está em `demanda[t - 1]`, e é por isso que `[t - 1]` aparece em várias linhas.
- **38:** cria o problema vazio `m`. Daqui em diante, tudo (variáveis, restrições, objetivo) é adicionado a ele.

## Linhas 40–66: variáveis

Cada variável fica num dicionário com chave (usina, período). Por exemplo, `gt["ANGRA1", 5]` é a geração de Angra no período 5.

**Térmicas (45–54):**

- **48:** `gt ≥ 0`, contínua. O teto não fica na variável; vem das restrições (10.9), porque depende de a usina estar ligada ou em trajetória.
- **49:** `u` binária: 1 se ligada.
- **50:** `y` contínua entre 0 e 1. Não precisa ser binária: como u e w são binárias, a (10.5) obriga y a sair 0 ou 1. Isso reduz o número de binárias, como no manual.
- **51:** `w` binária: 1 no período em que a unidade desliga.
- **53–54:** o truque de `t = 0`. O estado inicial do `operut.dat` (INIT) é guardado no mesmo dicionário, mas como **número**:
  - Angra: `u = 0`, `gt = 0` (desligada);
  - Baixada: `u = 1`, `gt = 510` (ligada).

  Assim, em t = 1 a expressão `u[i, t - 1]` funciona sem nenhum caso especial: o solver só enxerga um número no lugar da variável.

**Hidrelétricas (56–62):**

- **58:** `V[h, 1]` é o volume inicial, também um número: 15.923,7 hm³ em Furnas e 3.605,7 hm³ em Moraes.
- **60:** `q` entre 0 e o engolimento: 1.506 m³/s em Furnas, 1.272 m³/s em Moraes.
- **61:** `s` entre 0 e o vertimento máximo. Em Furnas o máximo é 0 (restrição 10186: proibido verter). Em Moraes é `None`, que no PySCIPOpt significa sem limite.
- **62:** `V[h, t + 1]` é o volume no **fim** do período t, que é o início do período seguinte. Os limites são:
  - mínimo: 5.620,5 hm³ em Furnas e 1.906,5 hm³ em Moraes (o volume da cota mínima de 655,3 m);
  - máximo: o volume máximo do cadastro.

  Cada usina tem 337 volumes: o primeiro é fixo e os outros 336 são variáveis.

**Déficit (64–66):** uma variável ≥ 0 por período, em MW.

No total são 5.040 variáveis, das quais 1.344 são binárias (u e w das duas térmicas nos 336 períodos).

---

## Linhas 69–131: térmicas

### O que u, y e w significam e quando valem 1

- **u** diz o estado da unidade em cada período: 1 = ligada, 0 = desligada (gerando zero). "Ligada" inclui as curvas de partida e de parada.
- **y** marca o período em que u muda de 0 para 1: a **partida**. É o **primeiro período fora do zero**, e a curva de subida começa ali.
- **w** marca o período em que u muda de 1 para 0: a **parada**. É o **primeiro período já em zero**, e a curva de descida aconteceu **antes** dele.

y e w valem 1 em **um único período**; não ficam ligados durante a curva inteira. Quem identifica "a usina está na curva" são as somas `partindo` e `parando`.

Baixada na solução:

| t | 153 | 154 | … | 173 | 174 … 330 | 331 | 332 | 333 |
|---|---|---|---|---|---|---|---|---|
| situação | desligada | partida | partida | partida | operação normal | parada | parada | desligada |
| gt (MW) | 0 | 15 | … | 320 | 320 | 250 | 100 | 0 |
| **u** | 0 | **1** | 1 | 1 | 1 | 1 | **1** | 0 |
| y | 0 | **1** | 0 | 0 | 0 | 0 | 0 | 0 |
| w | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **1** |

Essa assimetria explica as direções das somas:

- **A partida olha para trás:** a curva vem depois do y (houve um y nos últimos 20 períodos?).
- **A parada olha para a frente:** a curva vem antes do w (haverá um w nos próximos 2?). Em t = 331 a usina gera 250 MW porque existe um w em t + 2.

No modelo não existe um "momento da decisão" no tempo: o solver escolhe todas as variáveis de uma vez, para o horizonte inteiro. Ao colocar w = 1 em t = 333, ele automaticamente obriga 250 e 100 MW nos dois períodos anteriores, pelas restrições (10.8) e (10.9). Na operação real, a ordem de parar seria dada em t = 331, quando a descida começa.

### Linhas 70–95: as três funções auxiliares

Elas existem para não repetir as somas que aparecem em várias restrições. Nos exemplos, a Baixada tem trajetória de partida com NUp = 20 meias horas e de parada com NDn = 2.

**`partindo(i, t)` (70–73)** soma y(t) + y(t−1) + … + y(t−19), ou seja, as partidas dos últimos 20 períodos.

- O resultado é 1 se a usina partiu há menos de 20 meias horas (está na trajetória de partida) e 0 caso contrário.
- Nunca passa de 1, porque duas partidas ficam separadas por pelo menos Ton períodos.
- O `if t - k + 1 >= 1` ignora períodos antes do início do horizonte (lá y = 0).
- Na solução, a Baixada parte em t = 154, então `partindo` vale 1 de t = 154 a 173.

**`parando(i, t)` (76–79)** soma w(t+1) + w(t+2), ou seja, as paradas dos próximos 2 períodos.

- O resultado é 1 se a usina vai desligar daqui a 1 ou 2 meias horas (está na trajetória de parada).
- O `if t + k <= T` ignora períodos depois do fim do horizonte.
- Na solução, a Baixada desliga em t = 333, então `parando` vale 1 em t = 331 e 332.

**`potencia_da_trajetoria(i, t)` (82–95)** dá a potência que a curva impõe naquele período, ou 0 se a usina não está em trajetória.

O truque: quando o código monta o modelo, ninguém sabe ainda **quando** a usina vai partir ou parar; quem decide isso é o solver. Então, para cada período t, a função escreve **todas as possibilidades** de uma vez, cada uma multiplicada pela variável que diz "sim" (1) ou "não" (0). Como no máximo uma delas vale 1, a soma dá exatamente o valor da curva, ou zero.

**Linha 91, partida:**

```python
potencia += tr_up[k - 1] * y[i, t - k + 1]
```

Para cada k = 1, …, NUp, a linha pergunta: **"a usina partiu há k−1 períodos?"**

- `y[i, t - k + 1]` é a resposta (1 = sim).
- Se partiu, em t ela está na **k-ésima meia hora** da curva e deve gerar TrUp(k).
- `tr_up[k - 1]` é TrUp(k); o `- 1` é porque a lista começa na posição 0.

Exemplo: Baixada em t = 160, com curva de partida 15, 15, 15, 25, 25, 40, 40, 130, …, 320.

```
potencia = 15·y[160] + 15·y[159] + 15·y[158] + 25·y[157] + 25·y[156]
         + 40·y[155] + 40·y[154] + 130·y[153] + ... + 320·y[141]
```

| k | pergunta | variável | ponto da curva |
|---|---|---|---|
| 1 | partiu agora? | y[160] | 15 |
| 2 | partiu há 1 período? | y[159] | 15 |
| … | … | … | … |
| **7** | **partiu há 6 períodos?** | **y[154]** | **40** |
| 8 | partiu há 7 períodos? | y[153] | 130 |
| … | … | … | … |
| 20 | partiu há 19 períodos? | y[141] | 320 |

Como a Baixada parte em t = 154, só `y[154]` vale 1, e a soma dá **40 MW**: t = 160 é a 7ª meia hora contando 154, 155, …, 160.

**Linha 94, parada:**

```python
potencia += tr_dn[n_dn - k] * w[i, t + k]
```

Aqui a pergunta olha **para a frente**: **"a usina vai desligar daqui a k períodos?"**

- `w[i, t + k]` é a resposta.
- Se sim, faltam k meias horas para desligar. A curva de parada é contada **de trás para a frente** a partir do desligamento:
  - faltando k = NDn, a usina está no **primeiro** ponto da curva;
  - faltando k = 1, ela está no **último**.
- Por isso o ponto é TrDn(NDn−k+1), que na lista é `tr_dn[n_dn - k]`.

Exemplo: Baixada, curva de parada 250, 100 (NDn = 2), desligando em t = 333.

| período | expressão | valor |
|---|---|---|
| t = 331 | 100·w[332] + 250·w[333] | 250 (faltam 2: primeiro ponto) |
| t = 332 | 100·w[333] + 250·w[334] | 100 (falta 1: último ponto) |
| t = 333 | 100·w[334] + 250·w[335] | 0 (já desligou; u = 0 dá gt = 0) |

**Os dois tipos de "se" no código:**

- **Os `if` das linhas 90 e 93** (`t - k + 1 >= 1` e `t + k <= T`) são decididos quando o modelo é montado. Eles só pulam períodos que não existem: antes de t = 1 ou depois de t = 336.
- **O "se a usina partiu" de verdade** não pode ser um `if`, porque o valor de y só é conhecido depois que o solver resolve. Por isso vira uma multiplicação: número da curva × variável 0/1. É assim que se escreve uma condição de forma linear, que o MILP consegue tratar.

### Linhas 98–101: parâmetros de cada térmica

- **99:** rampa = 0,2 × (Pmax − Pmin): Angra 0,2 × 120 = 24 MW; Baixada 0,2 × 210 = 42 MW.
- **100–101:** tempos mínimos convertidos de horas para períodos (÷ 0,5): Angra 336/336; Baixada 144 ligada e 96 desligada.

### Linhas 105–106: partida e parada a partir do status (10.5 e 10.6)

As duas linhas amarram y e w ao status u. Juntas, garantem que **y = 1 só quando a usina liga** e **w = 1 só quando ela desliga**.

**Linha 105:** passando o w para o outro lado, fica y − w = u(t) − u(t−1). O lado direito é a mudança de status, e só há quatro situações:

| u(t−1) → u(t) | u(t) − u(t−1) | (y, w) que a 105 permite | Com a 106 |
|---|---|---|---|
| 0 → 1 (liga) | +1 | só (1, 0) | (1, 0): partida |
| 1 → 0 (desliga) | −1 | só (0, 1) | (0, 1): parada |
| 0 → 0 (segue desligada) | 0 | (0, 0) **ou (1, 1)** | (0, 0) |
| 1 → 1 (segue ligada) | 0 | (0, 0) **ou (1, 1)** | (0, 0) |

**Linha 106 (y + w ≤ 1):** quando o status não muda, a 105 aceita tanto (0, 0) quanto (1, 1), que seria uma partida e uma parada no mesmo período. A 106 proíbe isso. Sem ela, o solver poderia inventar manobras falsas: uma partida falsa liga a "chave" das rampas e suspende o limite de 42 MW.

**Consequências:**

1. **y pode ser contínua (linha 50):** com u e w binários, y sempre termina valendo exatamente 0 ou 1.
2. **Em t = 1, `u[i, 0]` é o número do estado inicial.** Angra começa desligada e liga em t = 1, então y(1) = 1. A Baixada começa ligada, segue ligada em t = 1 e 2 descendo pela trajetória, e só em t = 3 o status vai para 0, com w(3) = 1.

Eventos na solução (em todos os outros períodos, y = w = 0):

| Usina | t | u(t−1) → u(t) | y | w |
|---|---|---|---|---|
| Angra 1 | 1 | 0 → 1 | 1 | 0 |
| Baixada | 3 | 1 → 0 | 0 | 1 |
| Baixada | 154 | 0 → 1 | 1 | 0 |
| Baixada | 333 | 1 → 0 | 0 | 1 |

### Linhas 109–114: tempos mínimos ligada e desligada

**(10.3), linha 110:** Σ u(k), de k = t até t+janela−1, ≥ janela × (u(t) − u(t−1)).

- **Se a usina parte em t:** o lado direito vale `janela`. A soma de `janela` valores de u só chega a isso se **todos** forem 1, então a usina fica ligada a janela inteira.
- **Se não parte:** o lado direito é 0 ou negativo, e a restrição não restringe nada.
- **Por que a janela é cortada (linha 109):** `min(ton, T - t + 1)` encurta a janela perto do fim do horizonte. Sem isso, uma partida em t = 300 exigiria ficar ligada até t = 443, que não existe. Com o corte, a regra vira "fica ligada até o fim".
- **Na solução:** Angra parte em t = 1 com Ton = 336 e fica ligada o horizonte todo.

**(10.4), linha 114:** é o espelho da anterior. Se a usina para em t, então Σ (1 − u) ≥ janela, ou seja, todos os u da janela valem 0. A Baixada para em t = 3 e fica desligada pelo menos até t = 98; na solução, só volta em t = 154.

### Linhas 117–119: limites de geração com trajetórias, (10.8) e (10.9)

Com `normal = u − partindo − parando`, as duas restrições ficam: Pmin × normal + trajetória ≤ gt ≤ Pmax × normal + trajetória.

| Situação | u | partindo | parando | normal | trajetória | Resultado |
|---|---|---|---|---|---|---|
| desligada | 0 | 0 | 0 | 0 | 0 | gt = 0 |
| operação normal | 1 | 0 | 0 | 1 | 0 | Pmin ≤ gt ≤ Pmax |
| k-ésima meia hora da partida | 1 | 1 | 0 | 0 | TrUp(k) | gt = TrUp(k) |
| na parada | 1 | 0 | 1 | 0 | TrDn(…) | gt = TrDn(…) |

Na trajetória, os dois limites ficam iguais ao valor da curva, então a geração é forçada exatamente a ele. No período da própria parada, u = 0 e não há parada à frente, então cai na primeira linha: gt = 0.

### Linhas 124–127: rampas, (10.17) e (10.18)

- **`chave` (124):** vale 1 quando a usina está em alguma trajetória e 0 caso contrário.
- **`folga` (125):** Pmax − rampa.
- **Limite resultante:** com chave = 0 o limite é a rampa (42 MW na Baixada). Com chave = 1 é rampa + (Pmax − rampa) = Pmax (530 MW), ou seja, na prática não há limite.
- **126:** a subida de um período para o outro não pode passar do limite.
- **127:** o mesmo para a descida, com `+ w[i, t]` na chave (explicado abaixo).
- **Em t = 1:** `gt[i, 0]` é o número do estado inicial (510 MW na Baixada).

**Por que `w[i, t]` entra na chave da descida (decisão do usuário):** os degraus da curva de parada são pré-definidos pelo `rampas.dat`, e quase todos passam do limite de rampa de operação normal. A chave da fórmula original suspende a rampa nas meias horas da curva, mas **não no período em que a usina chega a zero**. Nesse período, a última queda (100 → 0 MW na Baixada, 122 → 0 em Angra) esbarra no limite de 42 MW (24 em Angra):

| t | Baixada | queda | chave (fórmula original) | limite | |
|---|---|---|---|---|---|
| 97 | 320 | 0 | 0 | 42 | ok |
| 98 | 250 | 70 | 1 (há parada em t+2) | livre | ok |
| 99 | 100 | 150 | 1 (há parada em t+1) | livre | ok |
| **100 (w = 1)** | **0** | **100** | **0** | **42** | **✘** |

Num teste forçando a Baixada a desligar em t = 100:

- com a fórmula original, o SCIP responde **"infeasible"**: nenhuma parada é possível, a Baixada ficaria ligada a semana toda e o custo iria a R$ 13,13 milhões;
- com a correção, o modelo resolve e produz a tabela acima.

Na partida o problema não existe, porque a chave inclui a própria meia hora da partida (y em t). A correção só libera a queda final até zero; nesse período a usina está desligada e a geração já é obrigatoriamente zero.

### Linhas 130–131: nada de parada no começo

A trajetória de parada ocupa os NDn períodos **antes** de w = 1. Se w fosse 1 em t = 1 ou 2, parte da curva cairia antes do início do horizonte, onde o modelo não enxerga nada. Por isso w = 0 em t ≤ NDn: t ≤ 2 na Baixada e t ≤ 9 em Angra. A primeira parada possível da Baixada é em t = 3, e foi a que o otimizador escolheu.

### A Baixada na solução, juntando tudo

| t | o que acontece | gt (MW) |
|---|---|---|
| 1–2 | trajetória de parada (parando = 1) | 250, 100 |
| 3 | w = 1, u = 0 | 0 |
| 4–153 | desligada (pelo menos 96 períodos, pela 10.4) | 0 |
| 154–173 | y = 1 em 154, trajetória de partida | 15 … 320 |
| 174–330 | operação normal (na prática fica em Pmin) | 320 |
| 331–332 | trajetória de parada | 250, 100 |
| 333–336 | w = 1 em 333, desligada | 0 |

---

## Linhas 133–149: hidrelétricas

### Linhas 134–135: atalhos

`furnas` e `moraes` só encurtam a escrita: `furnas["afluencia"]` em vez de `hidros["FURNAS"]["afluencia"]`.

### Linhas 136–140: balanço hídrico

Para cada período, o volume no fim é o volume no início mais o que entrou, menos o que saiu:

```
V(t+1) = V(t) + 0,0018 × (entrada − turbinada − vertida)
```

As vazões estão em m³/s e o volume em hm³. O 0,0018 (`HM3`) converte "m³/s durante meia hora" em hm³.

**Furnas (linha 138):** a entrada é a afluência natural de Furnas, já somando as usinas de montante (Camargos, Itutinga e Funil-Grande). `furnas["afluencia"][t - 1]` é a do período t. Exemplo com os números da solução em t = 1:

```
V(2) = 15.923,66 + 0,0018 × (1.090 − 1.405,14 − 0) = 15.923,66 − 0,57 = 15.923,10 hm³
```

Furnas turbinou mais do que recebeu, então o volume caiu um pouco.

**Moraes (linha 140):** a entrada é a afluência incremental de Moraes **mais tudo o que Furnas soltou no mesmo período** (q + s de Furnas). Não há tempo de viagem: a água sai de Furnas e chega a Moraes na mesma meia hora. É essa linha que faz a cascata. Exemplo em t = 1:

```
V(2) = 3.605,67 + 0,0018 × (146 + 1.405,14 + 0 − 1.272 − 0) = 3.605,67 + 0,50 = 3.606,17 hm³
```

Moraes recebeu mais do que turbinou, então o volume subiu.

### Linhas 142–147: limites de defluência (operuh.dat)

Defluência é tudo o que sai da usina: turbinada + vertida.

- **145:** q + s ≥ mínimo, que é 131 m³/s em Furnas (restrição 00443) e 149 m³/s em Moraes (00445). Garante uma vazão mínima no rio a jusante.
- **146–147:** q + s ≤ máximo, só quando existe máximo. Em Furnas é 1.440 m³/s (11145 até 01/11 e 11394 depois); em Moraes não há (`None`), então a restrição não é criada.

Como Furnas não pode verter (s ≤ 0, linha 61), o limite de 1.440 vale na prática para a turbinada. Fica abaixo do engolimento de 1.506 m³/s, e é por isso que Furnas nunca passa de 1.440 nos resultados.

### Linha 149: volume final

V(h, 337) ≥ volume inicial, para as duas usinas.

- **Por que existe:** a água não tem custo na função objetivo. Sem essa restrição, o modelo esvaziaria os reservatórios na semana para economizar térmica, sem pensar no futuro.
- **O que representa:** é o lugar da função de custo futuro (o corte do DECOMP), que entra numa próxima etapa.
- **Na solução:** a restrição fica ativa; os dois reservatórios terminam exatamente no volume inicial.

### O que não está nesta seção

- **Limites de volume e de turbinamento:** já foram colocados nas próprias variáveis (linhas 60–62).
- **Geração hidráulica:** gh = ρ × q aparece na restrição de demanda da próxima seção. Não há variável separada de geração hidráulica.

---

## Linhas 151–161: demanda e função objetivo

### Linhas 152–156: atendimento à demanda

```python
atendimento = {}
for t in PERIODOS:
    geracao_termica = quicksum(gt[i, t] for i in termicas)                     # 154
    geracao_hidraulica = quicksum(hidros[h]["rho"] * q[h, t] for h in hidros)  # 155
    atendimento[t] = m.addCons(geracao_termica + geracao_hidraulica + deficit[t] == demanda[t - 1])  # 156
```

- **154:** geração térmica no período t (Angra + Baixada).
- **155:** geração hidráulica = ρ × q de cada usina (0,8174 × q em Furnas, 0,3704 × q em Moraes). É aqui que a produtibilidade entra no modelo.
- **156:** em cada meia hora, tudo o que é gerado mais o déficit tem de ser igual à demanda. É barra única: não há rede, limite de linha nem perda.
- **O déficit** funciona como um "gerador de última instância" que custa 8.291,25 R$/MWh; só é usado quando não há outro jeito de atender.
- **152:** as restrições ficam guardadas no dicionário `atendimento` porque, no fim, o CMO é lido do dual delas (seção 7).

Conferindo com a solução em t = 1 (31/10 00:00):

```
Angra 122 + Baixada 250 + Furnas 1.148,53 + Moraes 471,15 + déficit 0 = 1.991,68 MW = demanda
```

### Linhas 158–161: função objetivo

```python
custo_termico    = Σ DT × CVU × gt              # 158
custo_vertimento = Σ 0,2 × 0,0018 × s           # 159
custo_deficit    = Σ DT × 8.291,25 × deficit    # 160
minimizar custo_termico + custo_vertimento + custo_deficit   # 161
```

- **158, custo térmico:** CVU está em R$/MWh e gt em MW; multiplicando por DT = 0,5 h, vira R$ por período. Exemplo: a Baixada a 320 MW durante meia hora custa 0,5 × 196,24 × 320 = R$ 31.398. A soma percorre as duas usinas e os 336 períodos.
- **159, penalidade de vertimento:** s (m³/s) × 0,0018 vira hm³, e × 0,2 vira R$. O valor é minúsculo de propósito: só evita verter à toa quando, de outra forma, seria indiferente. Na solução, ninguém verte.
- **160, custo de déficit:** mesma lógica do térmico, com 8.291,25 R$/MWh. Por ser muito caro, o déficit só aparece se faltar capacidade.
- **161:** minimiza a soma dos três.

**O que não está no objetivo:**

- **Custo da água:** a água é "de graça" aqui; o que impede de esvaziar os reservatórios é a restrição de volume final (linha 149). Com o corte do DECOMP, o custo futuro da água passa a aparecer no objetivo.
- **Custo de partida:** é zero por premissa, por isso o y não aparece aqui.

**O custo da solução, por parcela:**

| Parcela | R$ |
|---|---|
| Angra 1 | 3.200.075,46 |
| Baixada | 5.334.293,80 |
| Vertimento | 0 |
| Déficit | 0 |
| **Total** | **8.534.369,26** |

A Baixada gera só 8% da energia, mas responde por 62% do custo, porque o CVU dela é 6 vezes o de Angra.

---

## Linhas 163–188: solução

### Linhas 164–167: resolver

- **164, gap:** o SCIP mantém duas coisas durante a busca:
  - a melhor solução viável encontrada até agora (limite primal);
  - um limite inferior para o ótimo, que vem das relaxações lineares (limite dual).

  O gap é a diferença relativa entre os dois. Com `1e-5`, o SCIP para quando a solução está a menos de 0,001% do ótimo possível. Aqui o gap fecha em 0: a solução é **comprovadamente ótima**.
- **165:** limite de 15 minutos, só por segurança. Resolve em uns 30 s.
- **166:** `optimize()` resolve o MILP. Por dentro, o SCIP faz pré-solução (simplifica o problema), relaxação linear, cortes e branch-and-bound. É o log que aparece na tela.
- **167:** imprime o status, o custo e o gap.

### Linhas 169–182: guardar a solução numa tabela

A solução precisa ser copiada **antes** do cálculo do CMO, porque esse passo altera o modelo e apaga a solução do MILP. Colunas da tabela `resultado`:

- `t`, `inicio` (31/10 00:00 + 0,5 h × (t−1)) e `demanda`;
- `gt_` e `u_` de cada térmica. O `round` no u tira ruído numérico, como 0,9999999 → 1;
- `q_`, `s_` e `gh_` de cada hidrelétrica, com gh = ρ × q calculado ali mesmo;
- `V_`: volume no **fim** de cada período, que é o `V[h, t + 1]`;
- `deficit`.

### Linhas 184–188: guardar o compromisso

Monta uma lista de pares (variável, valor) com u, y e w de todos os períodos. É o que será fixado no cálculo do CMO.

---

## Linhas 190–206: CMO

**A ideia:** o CMO de um período é quanto o custo total aumentaria se a demanda daquele período subisse 1 MWh. Num problema linear, isso é o **dual** (preço-sombra) da restrição de atendimento. Só que o MILP tem variáveis inteiras e não tem dual. A prática padrão, a mesma do DESSEM, é:

1. fixar as decisões inteiras (quem está ligado, quando parte, quando para);
2. resolver de novo como LP;
3. ler os duais desse LP.

| Linha | O que faz | Por quê |
|---|---|---|
| 193 | `freeTransform()` | depois de resolver, o SCIP guarda uma versão transformada do problema; isso descarta essa versão e volta ao modelo original, que pode ser editado |
| 194–197 | cada u, y e w vira contínua, com mínimo = máximo = valor da solução | ficam fixas e não sobra nenhuma variável inteira, então o problema vira LP |
| 198 | gap = 0 | resolve até o fim, sem a tolerância do MILP |
| 199 | `disablecutoff` | o SCIP lembra a solução do MILP e pararia o LP ao atingir aquele custo, sem fechar a base; os duais sairiam inválidos (2e+99). Com isso, o LP é resolvido até o fim |
| 200 | pré-solução desligada | a pré-solução remove e transforma restrições; sem ela, os duais correspondem exatamente às restrições `atendimento` |
| 201–202 | heurísticas e propagação desligadas | também poderiam mexer no problema; num LP, não são necessárias |
| 203–204 | esconde o log e resolve | |
| 205 | imprime o custo do LP | conferência: tem de dar o mesmo do MILP (R$ 8.534.369,26), porque o compromisso fixado é o ótimo |
| 206 | CMO = dual ÷ DT | ver abaixo |

**Por que dividir por DT:** no objetivo, o custo de cada período é 0,5 × CVU × MW. Então +1 MW de demanda durante meia hora aumenta o custo em "dual" reais, e em R$/MWh isso fica dual ÷ 0,5. No resultado, o dual é 15,585 e o CMO fica 15,585 ÷ 0,5 = **31,17 R$/MWh**.

**Por que o CMO é 31,17 em todos os períodos:**

1. Com o compromisso fixo, 1 MW a mais em qualquer meia hora é atendido turbinando mais água naquele momento.
2. Essa água precisa ser reposta para o volume final não cair. Isso é feito gerando mais com Angra em algum período em que ela está abaixo de 640 MW, a 31,17 R$/MWh.
3. O reservatório liga todos os períodos, então a água vale o mesmo em qualquer um. O resultado é um CMO igual ao CVU de Angra.
4. A Baixada não define o CMO: é mais cara (196,24) e está parada no mínimo quando ligada.

Se houvesse déficit, o CMO daquele período iria a 8.291,25. Foi o que aconteceu no caso com perdas na produtibilidade.

---

## Linhas 208–212: saída

- **209–210:** pasta `saida` ao lado do script; é criada se não existir.
- **211:** arredonda para 4 casas e grava o CSV com `;` como separador e `,` como decimal, para abrir direto no Excel em português. `index=False` evita uma coluna extra de numeração.
- **212:** mostra onde salvou.
