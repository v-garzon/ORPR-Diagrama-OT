# Diagrama O-T · Bolígraf retràctil

Comanda de **100 peces** · règim calculat amb P10 → P20 · camí crític I → G → M → E → Q

## 1. Diagrama de procés

![Figura 1: diagrama de procés](<Diagrams/Image/ORPR%20Diagrama%20Procesos-2026-10-18-133655.png "Figura 1: diagrama de procés">)

El bolígraf es munta a partir de dues branques que s'uneixen al muntatge final (E). A la branca mecànica, el cos (I), el con (N) i el polsador (U) s'injecten en paral·lel i passen pel sobremoldejat del grip (G) i pel muntatge del mecanisme retràctil (M). A la branca de tinta, el portatintes (T) passa per l'omplert de tinta (L). Després del muntatge final, el bolígraf passa pel control de qualitat (Q).

| Op | Operació            | Temps (s/peça) | Rep material de |
| -- | -------------------- | --------------- | --------------- |
| I  | Inyección cuerpo    | 58.69           | —              |
| N  | Inyección cono      | 42.39           | —              |
| U  | Inyección pulsador  | 54.90           | —              |
| G  | Sobremoldeo grip     | 64.92           | I, N, U         |
| M  | Mecanismo retráctil | 65.08           | G               |
| T  | Montaje portatintas  | 73.73           | —              |
| L  | Llenado tinta        | 84.48           | T               |
| E  | Ensamblaje final     | 76.86           | M, L            |
| Q  | Control calidad      | 79.06           | E               |

## 2. Diagrama O-T

![Figura 1: diagrama O-T (Gantt) de les primeres 14 peces](<Diagrams\Image\ORPR%20Diagrama%20OT-2026-10-18-133709.png "diagrama O-T (Gantt) de les primeres 14 peces">)

Cada fila és una operació i cada barra, una peça. Cada barra comença quan acaba la tasca de la qual depèn. Els temps exactes s'han obtingut reproduint el diagrama en Python i ampliant-lo a 100 peces amb la mateixa regla. A partir de P10 el procés és estable: totes les operacions es llancen al ritme de L (Llenado tinta, 84.48 s), l'operació més lenta.

## 3. Resultats

| Paràmetre                        | Valor                                                                                                                              |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Termini de lliurament (100 peces) | 8677.65 s = 2 h 24 min 37.65 s                                                                                                     |
| Temps de cicle del procés        | 84.48 s/peça (coll d'ampolla: L · Llenado tinta, 84.48 s)                                                                        |
| Capacitat                         | 42.61 peces/h                                                                                                                      |
| Productivitat                     | 4.73 peces/h/recurs (9 recursos)                                                                                                   |
| Estoc                             | màx 1 peça per magatzem · màx 7 peces en cua a tota la línia · 4.85 bolígrafs de mitjana dins el procés en règim (màx 5) |
| Espera dels recursos              | 15384.07 s en total · la més gran: N (4071.68 s)                                                                                 |
| Equilibrat de la línia           | 78.9% (160.21 s d'espera per cicle sobre 9 × 84.48 s)                                                                             |

## 4. Teoria (P3-Id_fluxe) vs simulació (diagrama O-T)

| Magnitud                   | Fórmula (pàgina P3)           | Teoria     | Simulació | Diferència |
| -------------------------- | ------------------------------- | ---------- | ---------- | ----------- |
| Lead time 1a unitat        | LTu = Σt camí crític (p41)   | 344.61 s   | 344.61 s   | +0.00 s     |
| Termini (100 peces)        | LTu + CM·(Q−1) (p41)          | 8708.13 s  | 8677.65 s  | -30.48 s    |
| Temps de cicle             | C = CM = màx t (p17, p41)      | 84.48 s    | 84.48 s    | +0.00 s     |
| Capacitat                  | 3600 / C (p5)                   | 42.61 p/h  | 42.61 p/h  | +0.00 p/h   |
| Productivitat              | Capacitat / recursos (p5)       | 4.73 p/h/r | 4.73 p/h/r | +0.00 p/h/r |
| Estoc en procés (règim)  | WIP = LT / C [3] (p16)          | 4.08 bol   | 4.85 bol   | +0.77 bol   |
| Estoc màxim en procés \* | [7] (p19, p21)                  | 34.61 bol  | 5.00 bol   | —          |
| Retard acumulat D \*       | (CM − C1)·(Q−1) [10] (p20)   | 2553.21 s  | 64.75 s    | —          |
| Esperes dels recursos      | Σ (CM − t)·(Q−1) (p17, p46) | 15860.79 s | 15384.07 s | -476.72 s   |
| Equilibrat de la línia    | Σt / (recursos · CM)          | 78.9%      | 78.9%      | +0.0 pp     |

\* Hipòtesi de la fórmula: I empeny al seu ritme (C1 = 58.69 s), no al del coll d'ampolla; no és comparable directament amb el diagrama.

### Per què difereixen

- Termini: la fórmula suposa que, després de P1, totes les peces surten cada CM = 84.48 s. Al diagrama P2–P7 surten cada 79.06–81.10 s perquè L té 30.48 s d'avançament en arrencar (la seva P1 acaba a 158.21 s i E no la necessita fins a 188.69 s). Per això el termini real és 30.48 s més curt.
- Estoc en procés: la fórmula [3] amb LTu suposa que la peça no espera mai. En règim cada bolígraf passa 64.75 s en cues al camí crític (I→G 25.79 s, G→M 19.56 s, M→E 19.40 s, E→Q 0.00 s), que equivalen a 0.77 bolígrafs d'estoc (64.75 / 84.48).
- Estoc màxim i retard (\*): les fórmules [7] i [10] serien les d'una línia en què I empeny al seu ritme: l'estoc arribaria a 34.61 bolígrafs i l'última peça tardaria 2553.21 s més que la primera. Al diagrama I arrenca al ritme del coll d'ampolla (p18), per això l'estoc no creix i el temps de pas és constant a partir de P10; el retard de 64.75 s només es produeix a les primeres peces.
- Esperes: la fórmula suposa que cada recurs espera CM − t des de la 2a peça. En règim coincideixen (160.21 s per cicle a la teoria i 160.21 s al diagrama); la diferència ve de l'arrencada, on les primeres peces surten més ràpid que CM i els recursos esperen menys.

## 5. Resultats per operació (format P3 p36)

| Op | Operació            | t op (s) | Utilització | Lead time op (s) | Estoc màx (peces) | Estoc mitjà (peces) | Espera/peça (s) | Esperes (s) | Esperes teoria (s) |
| -- | -------------------- | -------- | ------------ | ---------------- | ------------------ | -------------------- | ---------------- | ----------- | ------------------ |
| I  | Inyección cuerpo    | 58.69    | 69.5%        | 8326.98          | —                 | —                   | 25.79            | 2457.98     | 2553.21            |
| N  | Inyección cono      | 42.39    | 50.2%        | 8310.68          | —                 | —                   | 42.09            | 4071.68     | 4166.91            |
| U  | Inyección pulsador  | 54.90    | 65.0%        | 8323.19          | —                 | —                   | 29.58            | 2833.19     | 2928.42            |
| G  | Sobremoldeo grip     | 64.92    | 76.8%        | 8359.00          | 3                  | 1.15                 | 19.56            | 1867.00     | 1936.44            |
| M  | Mecanismo retráctil | 65.08    | 77.0%        | 8378.72          | 1                  | 0.23                 | 19.40            | 1870.72     | 1920.60            |
| T  | Montaje portatintas  | 73.73    | 87.3%        | 8426.50          | —                 | —                   | 10.75            | 1053.50     | 1064.25            |
| L  | Llenado tinta        | 84.48    | 100.0%       | 8448.00          | 1                  | 0.13                 | 0.00             | 0.00        | 0.00               |
| E  | Ensamblaje final     | 76.86    | 91.0%        | 8409.90          | 2                  | 0.23                 | 7.62             | 723.90      | 754.38             |
| Q  | Control calidad      | 79.06    | 93.6%        | 8412.10          | 1                  | 0.00                 | 5.42             | 506.10      | 536.58             |

Estoc màx: peces que esperen a la vegada a l'entrada de l'operació durant la comanda (suma de les seves cues). Estoc mitjà, utilització i espera/peça: en règim. Esperes: temps total aturat entre peces dins la comanda. Esperes teoria: (CM − t)·(Q−1).

## 6. Estoc per magatzem

| Magatzem | Espera/peça en règim (s) | Estoc mitjà en règim (peces) | Espera màx (s) | Estoc màx (peces) | Estoc mitjà a la comanda (peces) |
| -------- | -------------------------- | ------------------------------ | --------------- | ------------------ | --------------------------------- |
| I → G   | 25.79                      | 0.31                           | 25.79           | 1                  | 0.29                              |
| N → G   | 42.09                      | 0.50                           | 42.09           | 1                  | 0.47                              |
| U → G   | 29.58                      | 0.35                           | 29.58           | 1                  | 0.33                              |
| G → M   | 19.56                      | 0.23                           | 19.56           | 1                  | 0.22                              |
| T → L   | 10.75                      | 0.13                           | 10.75           | 1                  | 0.12                              |
| M → E   | 19.40                      | 0.23                           | 19.40           | 1                  | 0.22                              |
| L → E   | 0.00                       | 0.00                           | 30.48           | 1                  | 0.01                              |
| E → Q   | 0.00                       | 0.00                           | 2.20            | 1                  | 0.00                              |

## 7. Entrada i sortida de les peces

Entrada: inici de la primera operació de la peça. Sortida: final de Q.

| Peça | Entrada (s) | Sortida (s) | Temps de pas (s) |
| ----- | ----------- | ----------- | ---------------- |
| P1    | 0.00        | 344.61      | 344.61           |
| P2    | 58.69       | 423.67      | 364.98           |
| P3    | 123.61      | 502.73      | 379.12           |
| P4    | 188.69      | 581.79      | 393.10           |
| P5    | 265.55      | 660.85      | 395.30           |
| …    |             |             |                  |
| P10   | 665.09      | 1074.45     | 409.36           |
| P20   | 1509.89     | 1919.25     | 409.36           |
| …    |             |             |                  |
| P99   | 8183.81     | 8593.17     | 409.36           |
| P100  | 8268.29     | 8677.65     | 409.36           |

A partir de P10 el temps de pas és constant (409.36 s).

## 8. Comprovació del diagrama

Cap recurs fa dues peces alhora i cap operació comença abans que les seves entrades.

## 9. Com es calcula i s'interpreta cada paràmetre (P3-Id_fluxe)

**Termini de lliurament.** Temps total necessari per lliurar el lot de producció (p6): des que comença la primera operació de P1 fins que l'última peça surt de Q. Al diagrama és el final de l'última barra de Q. Fórmula peça a peça (p41): LT = LTu + CM·(Q−1). LTu és el lead time de la 1a unitat, la suma dels temps del camí més llarg del flux, i les Q−1 peces restants surten al ritme de l'operació més lenta, CM.

**Temps de cicle.** Temps des que es lliura una unitat fins a la següent (p6). El del procés l'imposa l'operació més lenta, CM (p17, p41). No s'ha de confondre amb el temps de procés de cada operació. Al diagrama és la distància entre els finals de dues barres consecutives de Q en règim.

**Capacitat.** Producció del procés per unitat de temps (p5): 3600 / C peces/h. Al diagrama són les peces que surten de Q en una hora de règim (p36, unitats lliurades per hora).

**Productivitat.** Capacitat d'un recurs mesurada per unitat de temps i de recurs (p5): capacitat / nº de recursos. Depèn del que es compti com a recurs (màquines o operaris).

**Estoc (WIP).** Producte en elaboració que espera a ser processat (p6). Al diagrama és el temps entre el final d'una operació i l'inici de la següent per a la mateixa peça (les fletxes puntejades). Es relaciona amb el lead time per WIP = LT / C [3] (p16). Amb desequilibri, l'estoc creix si la primera operació empeny al seu ritme ([7], p19-21), però no creix si el seu ritme s'ajusta al de la més lenta (p18).

**Espera.** Temps que un lloc de treball està aturat esperant material (p17, «tiempos de paro»; p36, columna Esperas). Al diagrama són els buits dins de cada fila; el retard abans d'arrencar no compta. Si la línia va al ritme del coll d'ampolla, cada recurs espera CM − t per peça.

**Retard acumulat (D).** Quant més triga l'última peça que la primera a travessar el procés (p20-21). La fórmula D = (CM − C1)·(Q−1) suposa que la primera operació empeny al seu ritme C1.

**Lead time de l'operació.** Des que l'operació comença la primera peça fins que acaba l'última (p36-37).
