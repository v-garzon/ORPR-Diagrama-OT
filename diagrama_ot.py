#!/usr/bin/env python3
"""
Diagrama O-T · Bolígrafo retráctil (4 piezas)
=============================================

Reproduce el Gantt de Mermaid con tiempos exactos, calcula las métricas de ORPRO y las
compara con las fórmulas de la teoría (P3-Id_fluxe).

Semántica (la misma que Mermaid):
    "Pk :x_k, after y_j"  ->  la operación x de la pieza k empieza justo cuando termina y_j.
Los tiempos se calculan internamente en centésimas de segundo (enteros), así que no hay
error de redondeo acumulado aunque simules miles de piezas.

Uso desde Python:
    from diagrama_ot import metricas, imprimir_informe
    m = metricas(100)            # dict con todas las métricas y tablas
    imprimir_informe(m)
    m["termini_s"], m["ciclo_s"], m["capacidad_h"], m["productividad_h_recurso"]
    m["teoria"], m["simulacion"]  # mismas magnitudes según fórmula y según el diagrama
    m["por_operacion"]  # una fila por operación (formato P3 p36): lead time, estoc, esperas
    m["estoc"]          # una fila por almacén intermedio (origen -> destino)
    m["piezas"]         # [{pieza, entrada, salida, paso}, ...]
    m["operaciones"]    # [{pieza, op, nombre, inicio, fin, duracion}, ...]

Uso desde terminal:
    python diagrama_ot.py 100                 # informe
    python diagrama_ot.py 100 --detalle       # + entrada/salida de todas las piezas
    python diagrama_ot.py 100 --csv           # + tiempos exactos a CSV
    python diagrama_ot.py 100 --csv --excel   # CSV con ';' y coma decimal (Excel en español)
    python diagrama_ot.py 100 --mermaid       # + Gantt de Mermaid para 100 piezas
"""

from __future__ import annotations

import argparse
import csv
import textwrap
from pathlib import Path
from statistics import mean

# ─────────────────────────────────────────────────────────────────────────────
# DATOS DEL PROCESO
# ─────────────────────────────────────────────────────────────────────────────

# código: (nombre, tiempo de operación en s/pieza). El orden es el de las secciones del Gantt.
OPERACIONES = {
    "I": ("Inyección cuerpo", 58.69),
    "N": ("Inyección cono", 42.39),
    "U": ("Inyección pulsador", 54.90),
    "G": ("Sobremoldeo grip", 64.92),
    "M": ("Mecanismo retráctil", 65.08),
    "T": ("Montaje portatintas", 73.73),
    "L": ("Llenado tinta", 84.48),
    "E": ("Ensamblaje final", 76.86),
    "Q": ("Control calidad", 79.06),
}
ORDEN = list(OPERACIONES)

# Recursos (máquinas/operarios) por operación. Afecta a la productividad y al equilibrado.
RECURSOS = {op: 1 for op in OPERACIONES}

# Flujo de material (diagrama de procesos): qué operaciones alimentan a cada una.
# Define los almacenes intermedios (estoc), la espera de las piezas, el camino crítico
# y la comprobación de precedencias.
#   Mecánica: I, N, U (inyección en paralelo) -> G -> M -> E
#   Tinta:    T -> L -> E
#   E -> Q   (R, retrabajo y embalaje, no está en el diagrama O-T)
FLUJO = {
    "G": ["I", "N", "U"],  # las tres piezas inyectadas llegan al sobremoldeo
    "M": ["G"],
    "L": ["T"],
    "E": ["M", "L"],       # mecánica + carga de tinta
    "Q": ["E"],
}

# Arranque de P1..P10, copiado del Gantt. None = empieza en t=0; "G1" = after g1.
ARRANQUE = {
    "I": [None, "I1", "G1", "M1", "E1", "Q1", "Q2", "Q3", "Q4", "L7"],
    "N": [None, "I1", "G1", "M1", "E1", "Q1", "Q2", "Q3", "Q4", "L7"],
    "U": [None, "I1", "G1", "M1", "E1", "Q1", "Q2", "Q3", "Q4", "L7"],
    "G": ["I1", "G1", "M1", "E1", "Q1", "Q2", "Q3", "Q4", "L7", "L8"],
    "M": ["G1", "M1", "E1", "Q1", "Q2", "Q3", "Q4", "L7", "L8", "L9"],
    "T": [None, "T1", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8"],
    "L": ["T1", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9"],
    "E": ["M1", "E1", "Q1", "Q2", "Q3", "Q4", "L7", "L8", "L9", "L10"],
    "Q": ["E1", "Q1", "Q2", "Q3", "Q4", "Q5", "E7", "E8", "E9", "E10"],
}

# A partir de P11 (régimen): la operación op de la pieza n empieza al acabar ref de la pieza n - desfase.
#   i(10+k) after l(7+k)  ->  ("L", 3)
REGLA = {
    "I": ("L", 3),
    "N": ("L", 3),
    "U": ("L", 3),
    "G": ("L", 2),
    "M": ("L", 1),
    "T": ("L", 2),
    "L": ("L", 1),
    "E": ("L", 0),
    "Q": ("E", 0),
}

# ─────────────────────────────────────────────────────────────────────────────
# SIMULACIÓN
# ─────────────────────────────────────────────────────────────────────────────


def _cs(segundos: float) -> int:
    """Segundos -> centésimas de segundo (entero exacto)."""
    return round(segundos * 100)


def _duracion_cs(op: str) -> int:
    return _cs(OPERACIONES[op][1])


def referencia(op: str, n: int) -> tuple[str, int] | None:
    """De qué tarea depende el arranque de la operación op de la pieza n (None = t=0)."""
    if n <= len(ARRANQUE[op]):
        r = ARRANQUE[op][n - 1]
        return None if r is None else (r[0], int(r[1:]))
    ref, desfase = REGLA[op]
    return (ref, n - desfase)


def _simular_cs(n_piezas: int) -> dict[tuple[str, int], tuple[int, int]]:
    """{(op, pieza): (inicio, fin)} en centésimas de segundo."""
    t: dict[tuple[str, int], tuple[int, int]] = {}
    for n in range(1, n_piezas + 1):
        pendientes = list(ORDEN)
        while pendientes:
            avance = False
            for op in list(pendientes):
                ref = referencia(op, n)
                if ref is None:
                    t0 = 0
                elif ref in t:
                    t0 = t[ref][1]
                else:
                    continue
                t[op, n] = (t0, t0 + _duracion_cs(op))
                pendientes.remove(op)
                avance = True
            if not avance:
                raise ValueError(f"P{n}: referencia circular o a una pieza posterior en {pendientes}")
    return t


def simular(n_piezas: int) -> dict[tuple[str, int], tuple[float, float]]:
    """{(op, pieza): (inicio_s, fin_s)} con los tiempos exactos de cada operación."""
    return {k: (a / 100, b / 100) for k, (a, b) in _simular_cs(n_piezas).items()}


def camino_critico() -> tuple[list[str], int]:
    """Ruta más larga del flujo y su duración en centésimas (= lead time de la 1.ª unidad sin esperas)."""
    dur = {op: _duracion_cs(op) for op in ORDEN}
    fin_temprano: dict[str, int] = {}
    previa: dict[str, str | None] = {}

    def ef(op: str) -> int:
        if op not in fin_temprano:
            entradas = FLUJO.get(op, [])
            p = max(entradas, key=ef) if entradas else None
            fin_temprano[op] = (ef(p) if p else 0) + dur[op]
            previa[op] = p
        return fin_temprano[op]

    alimentan = {o for origenes in FLUJO.values() for o in origenes}
    final = max((op for op in ORDEN if op not in alimentan), key=ef)
    ruta, op = [], final
    while op:
        ruta.append(op)
        op = previa[op]
    return ruta[::-1], fin_temprano[final]


def _max_simultaneo(intervalos: list[tuple[int, int]]) -> int:
    """Máximo de intervalos [a, b) abiertos a la vez (a igual instante sale antes de entrar)."""
    ev = sorted([(a, 1) for a, b in intervalos if b > a] + [(b, -1) for a, b in intervalos if b > a])
    nivel = maximo = 0
    for _, d in ev:
        nivel += d
        maximo = max(maximo, nivel)
    return maximo


# ─────────────────────────────────────────────────────────────────────────────
# MÉTRICAS
# ─────────────────────────────────────────────────────────────────────────────


def metricas(n_piezas: int = 100, ventana: tuple[int, int] = (10, 20)) -> dict:
    """
    Métricas del diagrama O-T para un pedido de n_piezas, y las mismas según las fórmulas de la teoría.

    Las métricas de ritmo (ciclo, capacidad, productividad, esperas y estoc en régimen) se
    calculan como media entre las piezas ventana[0] y ventana[1] (por defecto P10 -> P20),
    simulando al menos ventana[1] piezas aunque el pedido sea más pequeño.
    Las de pedido (plazo, entrada/salida, máximos y totales) usan solo las n_piezas del pedido.
    """
    a, b = ventana
    if n_piezas < 1:
        raise ValueError("n_piezas debe ser >= 1")
    if not 1 <= a < b:
        raise ValueError("ventana debe cumplir 1 <= inicio < fin")

    N = n_piezas
    nsim = max(N, b)
    S = _simular_cs(nsim)
    ini = lambda op, n: S[op, n][0]  # noqa: E731
    fin = lambda op, n: S[op, n][1]  # noqa: E731
    dur = {op: _duracion_cs(op) for op in ORDEN}
    regimen = range(a + 1, b + 1)  # piezas usadas para las medias en régimen
    pedido = range(1, N + 1)

    salida = {n: fin("Q", n) for n in range(1, nsim + 1)}
    entrada = {n: min(ini(op, n) for op in ORDEN) for n in range(1, nsim + 1)}
    paso = {n: salida[n] - entrada[n] for n in range(1, nsim + 1)}

    # Ciclo = tiempo medio entre salidas consecutivas en régimen (centésimas, puede ser fraccionario)
    ciclo = (salida[b] - salida[a]) / (b - a)
    capacidad = 360000 / ciclo
    n_recursos = sum(RECURSOS.values())
    productividad = capacidad / n_recursos
    cuello = max(ORDEN, key=lambda op: dur[op] / RECURSOS[op])
    ciclo_por_op = {op: (ini(op, b) - ini(op, a)) / (b - a) for op in ORDEN}
    estable = all(abs(c - ciclo) < 0.5 for c in ciclo_por_op.values())

    piezas = [
        {"pieza": n, "entrada": entrada[n] / 100, "salida": salida[n] / 100, "paso": paso[n] / 100}
        for n in pedido
    ]
    operaciones = [
        {"pieza": n, "op": op, "nombre": OPERACIONES[op][0], "inicio": ini(op, n) / 100,
         "fin": fin(op, n) / 100, "duracion": dur[op] / 100}
        for n in pedido for op in ORDEN
    ]

    # Teoría: valores de referencia de las fórmulas
    ruta, ltu = camino_critico()
    cm = max(dur[op] / RECURSOS[op] for op in ORDEN)
    c1 = dur[ruta[0]]

    # Por operación (formato de la tabla de P3 p36)
    por_operacion = []
    for op in ORDEN:
        huecos_reg = [ini(op, n) - fin(op, n - 1) for n in regimen]
        huecos_ped = [ini(op, n) - fin(op, n - 1) for n in range(2, N + 1)]
        entradas = FLUJO.get(op, [])
        if entradas:
            est_max = _max_simultaneo([(fin(o, n), ini(op, n)) for o in entradas for n in pedido])
            est_medio = sum(mean(ini(op, n) - fin(o, n) for n in regimen) for o in entradas) / ciclo
        else:
            est_max = est_medio = None
        esp_teo = max(0.0, cm - dur[op] / RECURSOS[op])
        por_operacion.append({
            "op": op, "nombre": OPERACIONES[op][0], "t_op": dur[op] / 100,
            "utilizacion_regimen": dur[op] / RECURSOS[op] / ciclo,
            "lead_time_op": (fin(op, N) - ini(op, 1)) / 100,
            "estoc_max": est_max, "estoc_medio_regimen": est_medio,
            "espera_inicial": ini(op, 1) / 100,
            "espera_por_pieza_regimen": mean(huecos_reg) / 100,
            "espera_entre_piezas": sum(huecos_ped) / 100,
            "espera_por_pieza_teoria": esp_teo / 100,
            "espera_total_teoria": esp_teo * (N - 1) / 100,
        })

    # Estoc por almacén: piezas que han salido de 'origen' y esperan a entrar en 'destino'
    estoc = []
    for destino, origenes in FLUJO.items():
        for origen in origenes:
            w_reg = [ini(destino, n) - fin(origen, n) for n in regimen]
            w_ped = [ini(destino, n) - fin(origen, n) for n in pedido]
            estoc.append({
                "origen": origen, "destino": destino,
                "espera_pieza_regimen": mean(w_reg) / 100,
                "estoc_medio_regimen": mean(w_reg) / ciclo,       # Little: L = W / ciclo
                "espera_pieza_max": max(w_ped) / 100,
                "estoc_max": _max_simultaneo([(fin(origen, n), ini(destino, n)) for n in pedido]),
                "estoc_medio_pedido": sum(w_ped) / salida[N],     # media temporal en [0, plazo]
            })
    todas_las_colas = [(fin(o, n), ini(d, n)) for d, orgs in FLUJO.items() for o in orgs for n in pedido]

    # Teoría vs simulación
    if c1 < cm:   # [7]: la primera operación empuja a su ritmo
        wip_push = min(N, N * (1 - (c1 - ltu / N) / cm))
    else:
        wip_push = ltu / c1
    sum_t = sum(dur.values())
    teoria = {
        "lt_unidad_s": ltu / 100,
        "termini_s": (ltu + cm * (N - 1)) / 100,
        "ciclo_s": cm / 100,
        "capacidad_h": 360000 / cm,
        "productividad_h_recurso": 360000 / cm / n_recursos,
        "wip_regimen": ltu / cm,
        "wip_max_push": wip_push,
        "retraso_push_s": max(0.0, cm - c1) * (N - 1) / 100,
        "esperas_total_s": sum(r["espera_total_teoria"] for r in por_operacion),
        "equilibrado": sum_t / (n_recursos * cm),
    }
    paso_reg = mean(paso[n] for n in regimen)
    simulacion = {
        "lt_unidad_s": paso[1] / 100,
        "termini_s": salida[N] / 100,
        "ciclo_s": ciclo / 100,
        "capacidad_h": capacidad,
        "productividad_h_recurso": productividad,
        "wip_regimen": paso_reg / ciclo,
        "wip_max": _max_simultaneo([(entrada[n], salida[n]) for n in pedido]),
        "retraso_s": (paso[N] - paso[1]) / 100,
        "esperas_total_s": sum(r["espera_entre_piezas"] for r in por_operacion),
        "equilibrado": sum_t / (n_recursos * ciclo),
    }

    # Datos para explicar las diferencias
    rapidas = [n for n in range(2, N + 1) if salida[n] - salida[n - 1] < cm - 0.5]
    sucesor = next((d for d, orgs in FLUJO.items() if cuello in orgs), None)
    k = nsim
    while k > 1 and paso[k - 1] == paso[nsim]:
        k -= 1
    notas = {
        "ruta": ruta,
        "c1_s": c1 / 100,
        "cm_s": cm / 100,
        "salidas_rapidas": rapidas,
        "intervalos_rapidos_s": sorted({(salida[n] - salida[n - 1]) / 100 for n in rapidas}),
        "sucesor_cuello": sucesor,
        "avance_cuello_s": (ini(sucesor, 1) - fin(cuello, 1)) / 100 if sucesor else 0.0,
        "fin_cuello_p1_s": fin(cuello, 1) / 100,
        "ini_sucesor_p1_s": ini(sucesor, 1) / 100 if sucesor else 0.0,
        "espera_camino_regimen_s": (paso_reg - ltu) / 100,
        "esperas_camino": [(o, d, mean(ini(d, n) - fin(o, n) for n in regimen) / 100)
                           for o, d in zip(ruta, ruta[1:])],
        "paso_constante_desde": k,
        "espera_ciclo_teoria_s": sum(r["espera_por_pieza_teoria"] for r in por_operacion),
        "espera_ciclo_sim_s": sum(r["espera_por_pieza_regimen"] for r in por_operacion),
    }

    # Comprobación de que el diagrama es factible
    problemas = []
    for n in range(1, nsim + 1):
        for op in ORDEN:
            if n > 1 and RECURSOS[op] == 1 and ini(op, n) < fin(op, n - 1):
                problemas.append(f"{op}: P{n} empieza en {ini(op, n)/100:.2f} s pero P{n-1} "
                                 f"acaba en {fin(op, n-1)/100:.2f} s (mismo recurso)")
            for origen in FLUJO.get(op, []):
                if ini(op, n) < fin(origen, n):
                    problemas.append(f"{op}: P{n} empieza en {ini(op, n)/100:.2f} s pero {origen} "
                                     f"de P{n} acaba en {fin(origen, n)/100:.2f} s (precedencia)")

    return {
        "n_piezas": N,
        "ventana": ventana,
        "termini_s": salida[N] / 100,
        "ciclo_s": ciclo / 100,
        "capacidad_h": capacidad,
        "productividad_h_recurso": productividad,
        "n_recursos": n_recursos,
        "cuello_botella": cuello,
        "regimen_estable": estable,
        "ciclo_por_op_s": {op: c / 100 for op, c in ciclo_por_op.items()},
        "estoc_max_linea": _max_simultaneo(todas_las_colas),
        "teoria": teoria,
        "simulacion": simulacion,
        "notas": notas,
        "por_operacion": por_operacion,
        "estoc": estoc,
        "piezas": piezas,
        "operaciones": operaciones,
        "problemas": problemas,
    }


# ─────────────────────────────────────────────────────────────────────────────
# INFORME
# ─────────────────────────────────────────────────────────────────────────────

ANCHO = 114

DEFINICIONES = [
    ("Termini de lliurament",
     "Temps total necessari per lliurar el lot de producció (p6): des que comença la primera operació "
     "de P1 fins que l'última peça surt de Q. Al diagrama és el final de l'última barra de Q. Fórmula "
     "peça a peça (p41): LT = LTu + CM·(Q−1). LTu és el lead time de la 1a unitat, la suma dels temps "
     "del camí més llarg del flux, i les Q−1 peces restants surten al ritme de l'operació més lenta, CM."),
    ("Temps de cicle",
     "Temps des que es lliura una unitat fins a la següent (p6). El del procés l'imposa l'operació més "
     "lenta, CM (p17, p41). No s'ha de confondre amb el temps de procés de cada operació. Al diagrama "
     "és la distància entre els finals de dues barres consecutives de Q en règim."),
    ("Capacitat",
     "Producció del procés per unitat de temps (p5): 3600 / C peces/h. Al diagrama són les peces que "
     "surten de Q en una hora de règim (p36, unitats lliurades per hora)."),
    ("Productivitat",
     "Capacitat d'un recurs mesurada per unitat de temps i de recurs (p5): capacitat / nº de recursos. "
     "Depèn del que es compti com a recurs (màquines o operaris)."),
    ("Estoc (WIP)",
     "Producte en elaboració que espera a ser processat (p6). Al diagrama és el temps entre el final "
     "d'una operació i l'inici de la següent per a la mateixa peça (les fletxes puntejades). Es "
     "relaciona amb el lead time per WIP = LT / C [3] (p16). Amb desequilibri, l'estoc creix si la "
     "primera operació empeny al seu ritme ([7], p19-21), però no creix si el seu ritme s'ajusta al de "
     "la més lenta (p18)."),
    ("Espera",
     "Temps que un lloc de treball està aturat esperant material (p17, «tiempos de paro»; p36, columna "
     "Esperas). Al diagrama són els buits dins de cada fila; el retard abans d'arrencar no compta. Si "
     "la línia va al ritme del coll d'ampolla, cada recurs espera CM − t per peça."),
    ("Retard acumulat (D)",
     "Quant més triga l'última peça que la primera a travessar el procés (p20-21). La fórmula "
     "D = (CM − C1)·(Q−1) suposa que la primera operació empeny al seu ritme C1."),
    ("Lead time de l'operació",
     "Des que l'operació comença la primera peça fins que acaba l'última (p36-37)."),
]


def _hms(seg: float) -> str:
    h, r = divmod(seg, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)} h {int(m):02d} min {s:05.2f} s" if h >= 1 else f"{int(m)} min {s:05.2f} s"


def _parrafo(texto: str, sangria: str = "  ") -> str:
    return textwrap.fill(texto, width=ANCHO, initial_indent=sangria, subsequent_indent=sangria + "  ")


def _titulo(texto: str) -> None:
    print(f"\n{texto}\n" + "─" * ANCHO)


def imprimir_informe(m: dict, detalle: bool = False) -> None:
    N, (a, b) = m["n_piezas"], m["ventana"]
    cb = m["cuello_botella"]
    teo, sim, nt = m["teoria"], m["simulacion"], m["notas"]
    ruta = " → ".join(nt["ruta"])

    print("═" * ANCHO)
    print(f"DIAGRAMA O-T · BOLÍGRAF RETRÀCTIL — comanda de {N} peces")
    print(f"Règim calculat amb P{a} → P{b} ({b - a} intervals) · camí crític {ruta}"
          + ("" if m["regimen_estable"] else "   ⚠ el règim NO és estable en aquesta finestra"))
    print("═" * ANCHO)

    # 1 ───────────────────────────────────────────────────────────────────────
    _titulo("1. RESULTATS")
    for etiqueta, valor in _resultados(m):
        print(textwrap.fill(valor, width=ANCHO, initial_indent=f"{etiqueta:34}", subsequent_indent=" " * 34))

    # 2 ───────────────────────────────────────────────────────────────────────
    _titulo("2. TEORIA (P3-Id_fluxe) vs SIMULACIÓ (diagrama O-T)")
    print(f"{'Magnitud':27}{'Fórmula (pàgina P3)':30}{'Teoria':>14}{'Simulació':>14}{'Diferència':>14}")
    for nombre, formula, ft, fs, fd in _filas_teoria(m):
        print(f"{nombre:27}{formula:30}{ft:>14}{fs:>14}{fd:>14}")
    print(_parrafo(_nota_asterisco(m)))
    print("\n  Per què difereixen")
    for texto in _notas(m):
        print(_parrafo("· " + texto))
    _seccions_finals(m, detalle)


def _piezas_a_mostrar(m: dict, detalle: bool) -> list[dict | None]:
    """Todas las piezas, o una selección (inicio, ventana de régimen y final); None = salto."""
    files, (a, b) = m["piezas"], m["ventana"]
    if detalle or len(files) <= 12:
        return files
    mostrar = files[:5] + [None] + [f for f in files if f["pieza"] in (a, b)] + [None] + files[-2:]
    vistos, net = set(), []
    for f in mostrar:  # sin duplicados y conservando los separadores
        if f is None or f["pieza"] not in vistos:
            net.append(f)
            vistos.add(None if f is None else f["pieza"])
    return net


def _resultados(m: dict) -> list[tuple[str, str]]:
    """Resumen de resultados: (parámetro, valor) en catalán."""
    N, cb, sim, nt = m["n_piezas"], m["cuello_botella"], m["simulacion"], m["notas"]
    mas_espera = max(m["por_operacion"], key=lambda r: r["espera_entre_piezas"])
    max_alm = max(e["estoc_max"] for e in m["estoc"]) if m["estoc"] else 0
    return [
        (f"Termini de lliurament ({N} peces)", f"{m['termini_s']:.2f} s = {_hms(m['termini_s'])}"),
        ("Temps de cicle del procés", f"{m['ciclo_s']:.2f} s/peça (coll d'ampolla: {cb} · "
                                      f"{OPERACIONES[cb][0]}, {OPERACIONES[cb][1]:.2f} s)"),
        ("Capacitat", f"{m['capacidad_h']:.2f} peces/h"),
        ("Productivitat", f"{m['productividad_h_recurso']:.2f} peces/h/recurs ({m['n_recursos']} recursos)"),
        ("Estoc", f"màx {max_alm} peça per magatzem · màx {m['estoc_max_linea']} peces en cua a tota la "
                  f"línia · {sim['wip_regimen']:.2f} bolígrafs de mitjana dins el procés en règim "
                  f"(màx {sim['wip_max']})"),
        ("Espera dels recursos", f"{sim['esperas_total_s']:.2f} s en total · la més gran: "
                                 f"{mas_espera['op']} ({mas_espera['espera_entre_piezas']:.2f} s)"),
        ("Equilibrat de la línia", f"{sim['equilibrado']:.1%} ({nt['espera_ciclo_sim_s']:.2f} s d'espera per "
                                   f"cicle sobre {m['n_recursos']} × {m['ciclo_s']:.2f} s)"),
    ]


def _filas_teoria(m: dict) -> list[tuple[str, str, str, str, str]]:
    """Filas de la comparación teoría vs simulación: (magnitud, fórmula, teoría, simulación, diferencia)."""
    N, teo, sim = m["n_piezas"], m["teoria"], m["simulacion"]
    filas = []

    def fila(nombre, formula, t, s, unidad="s", dif=True, marca=""):
        ft = f"{t:.1%}" if unidad == "%" else f"{t:.2f}{unidad}"
        fs = f"{s:.1%}" if unidad == "%" else f"{s:.2f}{unidad}"
        if not dif:
            fd = "—"
        elif unidad == "%":
            fd = f"{(s - t) * 100:+.1f} pp"
        else:
            fd = f"{s - t:+.2f}{unidad}"
        filas.append((nombre + marca, formula, ft, fs, fd))

    fila("Lead time 1a unitat", "LTu = Σt camí crític (p41)", teo["lt_unidad_s"], sim["lt_unidad_s"], " s")
    fila(f"Termini ({N} peces)", "LTu + CM·(Q−1) (p41)", teo["termini_s"], sim["termini_s"], " s")
    fila("Temps de cicle", "C = CM = màx t (p17, p41)", teo["ciclo_s"], sim["ciclo_s"], " s")
    fila("Capacitat", "3600 / C (p5)", teo["capacidad_h"], sim["capacidad_h"], " p/h")
    fila("Productivitat", "Capacitat / recursos (p5)", teo["productividad_h_recurso"],
         sim["productividad_h_recurso"], " p/h/r")
    fila("Estoc en procés (règim)", "WIP = LT / C [3] (p16)", teo["wip_regimen"], sim["wip_regimen"], " bol")
    fila("Estoc màxim en procés", "[7] (p19, p21)", teo["wip_max_push"], sim["wip_max"], " bol",
         dif=False, marca=" *")
    fila("Retard acumulat D", "(CM − C1)·(Q−1) [10] (p20)", teo["retraso_push_s"], sim["retraso_s"], " s",
         dif=False, marca=" *")
    fila("Esperes dels recursos", "Σ (CM − t)·(Q−1) (p17, p46)", teo["esperas_total_s"],
         sim["esperas_total_s"], " s")
    fila("Equilibrat de la línia", "Σt / (recursos · CM)", teo["equilibrado"], sim["equilibrado"], "%")
    return filas


def _nota_asterisco(m: dict) -> str:
    nt = m["notas"]
    return (f"* Hipòtesi de la fórmula: {nt['ruta'][0]} empeny al seu ritme (C1 = {nt['c1_s']:.2f} s), "
            "no al del coll d'ampolla; no és comparable directament amb el diagrama.")


def _notas(m: dict) -> list[str]:
    """Explicación de las diferencias entre teoría y simulación."""
    N, cb, teo, sim, nt = m["n_piezas"], m["cuello_botella"], m["teoria"], m["simulacion"], m["notas"]
    notas = []
    d_termini = sim["termini_s"] - teo["termini_s"]
    if abs(d_termini) < 0.005:
        txt = "Termini: coincideixen."
    elif d_termini < 0 and nt["salidas_rapidas"]:
        r = nt["salidas_rapidas"]
        iv = nt["intervalos_rapidos_s"]
        rango = f"{iv[0]:.2f}" if len(iv) == 1 else f"{iv[0]:.2f}–{iv[-1]:.2f}"
        txt = (f"Termini: la fórmula suposa que, després de P1, totes les peces surten cada CM = "
               f"{nt['cm_s']:.2f} s. Al diagrama P{r[0]}–P{r[-1]} surten cada {rango} s perquè "
               f"{cb} té {nt['avance_cuello_s']:.2f} s d'avançament en arrencar (la seva P1 acaba a "
               f"{nt['fin_cuello_p1_s']:.2f} s i {nt['sucesor_cuello']} no la necessita fins a "
               f"{nt['ini_sucesor_p1_s']:.2f} s). Per això el termini real és {-d_termini:.2f} s més curt.")
    else:
        txt = (f"Termini: el diagrama dona {d_termini:+.2f} s respecte a la fórmula per retards o "
               f"avançaments en l'arrencada.")
    notas.append(txt)

    esperas = ", ".join(f"{o}→{d} {w:.2f} s" for o, d, w in nt["esperas_camino"])
    notas.append(
        f"Estoc en procés: la fórmula [3] amb LTu suposa que la peça no espera mai. En règim cada "
        f"bolígraf passa {nt['espera_camino_regimen_s']:.2f} s en cues al camí crític ({esperas}), que "
        f"equivalen a {nt['espera_camino_regimen_s'] / m['ciclo_s']:.2f} bolígrafs d'estoc "
        f"({nt['espera_camino_regimen_s']:.2f} / {m['ciclo_s']:.2f}).")
    if N < 2:
        return notas
    notas.append(
        f"Estoc màxim i retard (*): les fórmules [7] i [10] serien les d'una línia en què "
        f"{nt['ruta'][0]} empeny al seu ritme: l'estoc arribaria a {teo['wip_max_push']:.2f} bolígrafs "
        f"i l'última peça tardaria {teo['retraso_push_s']:.2f} s més que la primera. Al diagrama "
        f"{nt['ruta'][0]} arrenca al ritme del coll d'ampolla (p18), per això l'estoc no creix i el "
        f"temps de pas és constant a partir de P{nt['paso_constante_desde']}; el retard de "
        f"{sim['retraso_s']:.2f} s només es produeix a les primeres peces.")
    notas.append(
        f"Esperes: la fórmula suposa que cada recurs espera CM − t des de la 2a peça. En règim "
        f"coincideixen ({nt['espera_ciclo_teoria_s']:.2f} s per cicle a la teoria i "
        f"{nt['espera_ciclo_sim_s']:.2f} s al diagrama); la diferència ve de l'arrencada, on les "
        f"primeres peces surten més ràpid que CM i els recursos esperen menys.")
    return notas


def _seccions_finals(m: dict, detalle: bool) -> None:
    (a, b) = m["ventana"]
    po = m["por_operacion"]

    # 3 ───────────────────────────────────────────────────────────────────────
    _titulo("3. PER OPERACIÓ (format P3 p36)")
    print(f"{'Op':4}{'Recurs':21}{'t op':>7}{'Util.':>8}{'Lead t. op':>12}{'Estoc màx':>11}"
          f"{'Estoc mitjà':>13}{'Espera/peça':>13}{'Esperes':>11}{'Esperes teo.':>14}")
    for r in po:
        emax = "—" if r["estoc_max"] is None else f"{r['estoc_max']} p"
        emed = "—" if r["estoc_medio_regimen"] is None else f"{r['estoc_medio_regimen']:.2f} p"
        print(f"{r['op']:4}{r['nombre']:21}{r['t_op']:>7.2f}{r['utilizacion_regimen']:>8.1%}"
              f"{r['lead_time_op']:>10.2f} s{emax:>11}{emed:>13}{r['espera_por_pieza_regimen']:>11.2f} s"
              f"{r['espera_entre_piezas']:>9.2f} s{r['espera_total_teoria']:>12.2f} s")
    print(_parrafo("Estoc màx: peces que esperen a la vegada a l'entrada de l'operació durant la comanda "
                   "(suma de les seves cues). Estoc mitjà, utilització i espera/peça: en règim. Esperes: "
                   "total entre peces dins la comanda; Esperes teo.: (CM − t)·(Q−1).", "  "))

    # 4 ───────────────────────────────────────────────────────────────────────
    _titulo("4. ESTOC PER MAGATZEM")
    print(f"{'':10}{'— règim (P%d→P%d) —' % (a, b):^28}{'— comanda —':^36}")
    print(f"{'Magatzem':10}{'espera/peça':>14}{'estoc mitjà':>14}{'espera màx':>12}{'estoc màx':>11}"
          f"{'estoc mitjà':>13}")
    for e in m["estoc"]:
        print(f"{e['origen'] + ' → ' + e['destino']:10}{e['espera_pieza_regimen']:>12.2f} s"
              f"{e['estoc_medio_regimen']:>12.2f} p{e['espera_pieza_max']:>10.2f} s"
              f"{e['estoc_max']:>9d} p{e['estoc_medio_pedido']:>11.2f} p")

    # 5 ───────────────────────────────────────────────────────────────────────
    _titulo("5. PECES (entrada = inici de la primera operació, sortida = final de Q)")
    print(f"{'Peça':>6}{'entrada (s)':>14}{'sortida (s)':>14}{'temps de pas (s)':>18}")
    for f in _piezas_a_mostrar(m, detalle):
        if f is None:
            print(f"{'…':>6}")
            continue
        print(f"{'P' + str(f['pieza']):>6}{f['entrada']:>14.2f}{f['salida']:>14.2f}{f['paso']:>18.2f}")

    # 6 ───────────────────────────────────────────────────────────────────────
    _titulo("6. COMPROVACIÓ DEL DIAGRAMA")
    if m["problemas"]:
        print(f"  ⚠ {len(m['problemas'])} conflictes:")
        for p in m["problemas"][:20]:
            print("   -", p)
    else:
        print("  Cap recurs fa dues peces alhora i cap operació comença abans que les seves entrades.")

    # 7 ───────────────────────────────────────────────────────────────────────
    _titulo("7. COM ES CALCULA I S'INTERPRETA CADA PARÀMETRE (P3-Id_fluxe)")
    for nombre, texto in DEFINICIONES:
        print(_parrafo(f"{nombre}. {texto}"))
    print()


# ─────────────────────────────────────────────────────────────────────────────
# EXPORTACIÓN
# ─────────────────────────────────────────────────────────────────────────────


def a_markdown(m: dict) -> str:
    """Informe completo en Markdown (en catalán) para pasarlo a Word, con huecos para las dos figuras."""
    N, (a, b) = m["n_piezas"], m["ventana"]
    cb, nt, sim = m["cuello_botella"], m["notas"], m["simulacion"]
    esc = lambda s: s.replace("*", "\\*")  # noqa: E731
    md: list[str] = []
    add = md.append

    def tabla(cabecera, filas):
        add("| " + " | ".join(cabecera) + " |")
        add("|" + "|".join("---" for _ in cabecera) + "|")
        for f in filas:
            add("| " + " | ".join(str(x) for x in f) + " |")
        add("")

    add("# Diagrama O-T · Bolígraf retràctil\n")
    add(f"Comanda de **{N} peces** · règim calculat amb P{a} → P{b} · camí crític {' → '.join(nt['ruta'])}\n")

    add("## 1. Diagrama de procés\n")
    add('![Figura 1: diagrama de procés](./Diagrams/Image/ORPR%20Diagrama%20Procesos-2026-10-18-133655.png "Figura 1: diagrama de procés")\n')
    add("El bolígraf es munta a partir de dues branques que s'uneixen al muntatge final (E). A la branca "
        "mecànica, el cos (I), el con (N) i el polsador (U) s'injecten en paral·lel i passen pel sobremoldejat "
        "del grip (G) i pel muntatge del mecanisme retràctil (M). A la branca de tinta, el portatintes (T) "
        "passa per l'omplert de tinta (L). Després del muntatge final, el bolígraf passa pel control de "
        "qualitat (Q).\n")
    tabla(["Op", "Operació", "Temps (s/peça)", "Rep material de"],
          [(op, OPERACIONES[op][0], f"{OPERACIONES[op][1]:.2f}", ", ".join(FLUJO.get(op, [])) or "—")
           for op in ORDEN])

    add("## 2. Diagrama O-T\n")
    add('![Figura 1: diagrama O-T (Gantt) de les primeres 14 peces](./Diagrams/Image/ORPR%20Diagrama%20OT-2026-10-18-133709.png "diagrama O-T (Gantt) de les primeres 14 peces")\n')
    add(f"Cada fila és una operació i cada barra, una peça. Cada barra comença quan acaba la tasca de la qual "
        f"depèn. Els temps exactes s'han obtingut reproduint el diagrama en Python i ampliant-lo a {N} peces "
        f"amb la mateixa regla. A partir de P{nt['paso_constante_desde']} el procés és estable: totes les "
        f"operacions es llancen al ritme de {cb} ({OPERACIONES[cb][0]}, {OPERACIONES[cb][1]:.2f} s), "
        f"l'operació més lenta.\n")

    add("## 3. Resultats\n")
    tabla(["Paràmetre", "Valor"], _resultados(m))

    add("## 4. Teoria (P3-Id_fluxe) vs simulació (diagrama O-T)\n")
    tabla(["Magnitud", "Fórmula (pàgina P3)", "Teoria", "Simulació", "Diferència"],
          [(esc(n), f, t, s, d) for n, f, t, s, d in _filas_teoria(m)])
    add(esc(_nota_asterisco(m)) + "\n")
    add("### Per què difereixen\n")
    for texto in _notas(m):
        add("- " + esc(texto))
    add("")

    add("## 5. Resultats per operació (format P3 p36)\n")
    filas = []
    for r in m["por_operacion"]:
        filas.append((
            r["op"], r["nombre"], f"{r['t_op']:.2f}", f"{r['utilizacion_regimen']:.1%}",
            f"{r['lead_time_op']:.2f}",
            "—" if r["estoc_max"] is None else r["estoc_max"],
            "—" if r["estoc_medio_regimen"] is None else f"{r['estoc_medio_regimen']:.2f}",
            f"{r['espera_por_pieza_regimen']:.2f}", f"{r['espera_entre_piezas']:.2f}",
            f"{r['espera_total_teoria']:.2f}",
        ))
    tabla(["Op", "Operació", "t op (s)", "Utilització", "Lead time op (s)", "Estoc màx (peces)",
           "Estoc mitjà (peces)", "Espera/peça (s)", "Esperes (s)", "Esperes teoria (s)"], filas)
    add("Estoc màx: peces que esperen a la vegada a l'entrada de l'operació durant la comanda (suma de les "
        "seves cues). Estoc mitjà, utilització i espera/peça: en règim. Esperes: temps total aturat entre "
        "peces dins la comanda. Esperes teoria: (CM − t)·(Q−1).\n")

    add("## 6. Estoc per magatzem\n")
    tabla(["Magatzem", "Espera/peça en règim (s)", "Estoc mitjà en règim (peces)", "Espera màx (s)",
           "Estoc màx (peces)", "Estoc mitjà a la comanda (peces)"],
          [(f"{e['origen']} → {e['destino']}", f"{e['espera_pieza_regimen']:.2f}",
            f"{e['estoc_medio_regimen']:.2f}", f"{e['espera_pieza_max']:.2f}", e["estoc_max"],
            f"{e['estoc_medio_pedido']:.2f}") for e in m["estoc"]])

    add("## 7. Entrada i sortida de les peces\n")
    add("Entrada: inici de la primera operació de la peça. Sortida: final de Q.\n")
    tabla(["Peça", "Entrada (s)", "Sortida (s)", "Temps de pas (s)"],
          [("…", "", "", "") if f is None else
           (f"P{f['pieza']}", f"{f['entrada']:.2f}", f"{f['salida']:.2f}", f"{f['paso']:.2f}")
           for f in _piezas_a_mostrar(m, False)])
    if N >= nt["paso_constante_desde"]:
        add(f"A partir de P{nt['paso_constante_desde']} el temps de pas és constant "
            f"({m['piezas'][-1]['paso']:.2f} s).\n")

    add("## 8. Comprovació del diagrama\n")
    if m["problemas"]:
        add(f"El diagrama té {len(m['problemas'])} conflictes:\n")
        for p in m["problemas"][:20]:
            add("- " + p)
        add("")
    else:
        add("Cap recurs fa dues peces alhora i cap operació comença abans que les seves entrades.\n")

    add("## 9. Com es calcula i s'interpreta cada paràmetre (P3-Id_fluxe)\n")
    for nombre, texto in DEFINICIONES:
        add(f"**{nombre}.** {texto}\n")
    return "\n".join(md)


def exportar_csv(m: dict, carpeta: str | Path = ".", excel: bool = False) -> list[Path]:
    """Escribe ot_piezas.csv y ot_operaciones.csv. excel=True -> ';' y coma decimal."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    sep = ";" if excel else ","
    fmt = (lambda x: f"{x:.2f}".replace(".", ",")) if excel else (lambda x: f"{x:.2f}")
    rutas = []
    tablas = {
        "ot_piezas.csv": (["pieza", "entrada", "salida", "paso"], m["piezas"]),
        "ot_operaciones.csv": (["pieza", "op", "nombre", "inicio", "fin", "duracion"], m["operaciones"]),
    }
    for nombre, (cols, filas) in tablas.items():
        ruta = carpeta / nombre
        with ruta.open("w", newline="", encoding="utf-8-sig" if excel else "utf-8") as f:
            w = csv.writer(f, delimiter=sep)
            w.writerow(cols)
            for fila in filas:
                w.writerow([fmt(fila[c]) if isinstance(fila[c], float) else fila[c] for c in cols])
        rutas.append(ruta)
    return rutas


def a_mermaid(n_piezas: int) -> str:
    """Gantt de Mermaid equivalente para n_piezas (mismo formato que el original)."""
    estilos = {1: "", 2: "active, ", 3: "done, ", 0: "crit, "}
    tick = "1minute" if n_piezas <= 30 else "10minute"
    lineas = [
        "---", "displayMode: compact", "config:", "  gantt:", "    leftPadding: 190",
        "    barHeight: 22", "---", "gantt",
        "    title Diagrama O-T · Bolígrafo retráctil (4 piezas)",
        "    dateFormat X", "    axisFormat %M:%S", f"    tickInterval {tick}",
    ]
    for op in ORDEN:
        nombre, t = OPERACIONES[op]
        lineas += ["", f"    section {op} · {nombre}"]
        for n in range(1, n_piezas + 1):
            ref = referencia(op, n)
            arranque = "0" if ref is None else f"after {ref[0].lower()}{ref[1]}"
            lineas.append(f"    P{n} :{estilos[n % 4]}{op.lower()}{n}, {arranque}, {t:.2f}s")
    return "\n".join(lineas) + "\n"


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Métricas del diagrama O-T del bolígrafo retráctil")
    p.add_argument("piezas", nargs="?", type=int, default=100, help="piezas del pedido (por defecto 100)")
    p.add_argument("--ventana", nargs=2, type=int, default=(10, 20), metavar=("DESDE", "HASTA"),
                   help="piezas para medir el régimen (por defecto 10 20)")
    p.add_argument("--detalle", action="store_true", help="mostrar entrada/salida de todas las piezas")
    p.add_argument("--csv", action="store_true", help="exportar tiempos exactos a CSV")
    p.add_argument("--excel", action="store_true", help="CSV con ';' y coma decimal")
    p.add_argument("--mermaid", action="store_true", help="guardar el Gantt de Mermaid para N piezas")
    p.add_argument("--md", action="store_true", help="guardar el informe en Markdown (para Word)")
    args = p.parse_args()

    m = metricas(args.piezas, tuple(args.ventana))
    imprimir_informe(m, detalle=args.detalle)
    if args.csv:
        for ruta in exportar_csv(m, excel=args.excel):
            print("CSV:", ruta)
    if args.mermaid:
        ruta = Path(f"diagrama_ot_P{args.piezas}.mmd")
        ruta.write_text(a_mermaid(args.piezas), encoding="utf-8")
        print("Mermaid:", ruta)
    if args.md:
        ruta = Path(f"informe_{args.piezas}_peces.md")
        ruta.write_text(a_markdown(m), encoding="utf-8")
        print("Markdown:", ruta)