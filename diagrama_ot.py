#!/usr/bin/env python3
"""
Diagrama O-T · Bolígrafo retráctil (4 piezas)
=============================================

Reproduce el Gantt de Mermaid con tiempos exactos y calcula las métricas de ORPRO.

Semántica (la misma que Mermaid):
    "Pk :x_k, after y_j"  ->  la operación x de la pieza k empieza justo cuando termina y_j.
Los tiempos se calculan internamente en centésimas de segundo (enteros), así que no hay
error de redondeo acumulado aunque simules miles de piezas.

Uso desde Python:
    from diagrama_ot import metricas, imprimir_informe
    m = metricas(100)            # dict con todas las métricas y tablas
    imprimir_informe(m)
    m["termini_s"], m["ciclo_s"], m["capacidad_h"], m["productividad_h_recurso"]
    m["piezas"]        # [{pieza, entrada, salida, paso}, ...]
    m["operaciones"]   # [{pieza, op, nombre, inicio, fin, duracion}, ...]
    m["estoc"]         # una fila por almacén intermedio (origen -> destino)
    m["esperas"]       # una fila por recurso

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

# Recursos (máquinas/operarios) por operación. Solo afecta a la productividad.
RECURSOS = {op: 1 for op in OPERACIONES}

# Flujo de material (diagrama de procesos): qué operaciones alimentan a cada una.
# Define los almacenes intermedios (estoc), la espera de las piezas y la comprobación de precedencias.
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


# ─────────────────────────────────────────────────────────────────────────────
# MÉTRICAS
# ─────────────────────────────────────────────────────────────────────────────


def metricas(n_piezas: int = 100, ventana: tuple[int, int] = (10, 20)) -> dict:
    """
    Métricas del diagrama O-T para un pedido de n_piezas.

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

    salida = {n: fin("Q", n) for n in range(1, nsim + 1)}
    entrada = {n: min(ini(op, n) for op in ORDEN) for n in range(1, nsim + 1)}

    # Ciclo = tiempo medio entre salidas consecutivas en régimen (centésimas, puede ser fraccionario)
    ciclo = (salida[b] - salida[a]) / (b - a)
    capacidad = 3600 / (ciclo / 100)
    n_recursos = sum(RECURSOS.values())
    productividad = capacidad / n_recursos
    cuello = max(ORDEN, key=lambda op: dur[op] / RECURSOS[op])
    ciclo_por_op = {op: (ini(op, b) - ini(op, a)) / (b - a) for op in ORDEN}
    estable = all(abs(c - ciclo) < 0.5 for c in ciclo_por_op.values())

    regimen = range(a + 1, b + 1)  # piezas usadas para las medias en régimen
    pedido = range(1, N + 1)

    piezas = [
        {"pieza": n, "entrada": entrada[n] / 100, "salida": salida[n] / 100,
         "paso": (salida[n] - entrada[n]) / 100}
        for n in pedido
    ]
    operaciones = [
        {"pieza": n, "op": op, "nombre": OPERACIONES[op][0], "inicio": ini(op, n) / 100,
         "fin": fin(op, n) / 100, "duracion": dur[op] / 100}
        for n in pedido for op in ORDEN
    ]

    # Esperas de los recursos (huecos en cada fila del Gantt)
    esperas = []
    for op in ORDEN:
        huecos_reg = [ini(op, n) - fin(op, n - 1) for n in regimen]
        huecos_ped = [ini(op, n) - fin(op, n - 1) for n in range(2, N + 1)]
        esperas.append({
            "op": op, "nombre": OPERACIONES[op][0], "t_op": dur[op] / 100,
            "espera_inicial": ini(op, 1) / 100,
            "espera_entre_piezas": sum(huecos_ped) / 100,
            "espera_por_pieza_regimen": mean(huecos_reg) / 100,
            "utilizacion_regimen": dur[op] / ciclo,
        })

    # Estoc: piezas que han salido de 'origen' y esperan a entrar en 'destino'
    estoc = []
    for destino, origenes in FLUJO.items():
        for origen in origenes:
            w_reg = [ini(destino, n) - fin(origen, n) for n in regimen]
            w_ped = [ini(destino, n) - fin(origen, n) for n in pedido]
            eventos = sorted([(fin(origen, n), +1) for n in pedido] + [(ini(destino, n), -1) for n in pedido])
            nivel = maximo = 0
            for _, d in eventos:  # a igual instante sale antes de entrar (-1 < +1)
                nivel += d
                maximo = max(maximo, nivel)
            estoc.append({
                "origen": origen, "destino": destino,
                "espera_pieza_regimen": mean(w_reg) / 100,
                "estoc_medio_regimen": mean(w_reg) / ciclo,       # Little: L = W / ciclo
                "espera_pieza_max": max(w_ped) / 100,
                "estoc_max": maximo,
                "estoc_medio_pedido": sum(w_ped) / salida[N],     # media temporal en [0, plazo]
            })

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
        "piezas": piezas,
        "operaciones": operaciones,
        "esperas": esperas,
        "estoc": estoc,
        "problemas": problemas,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SALIDAS
# ─────────────────────────────────────────────────────────────────────────────


def _hms(seg: float) -> str:
    h, r = divmod(seg, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)} h {int(m):02d} min {s:05.2f} s" if h >= 1 else f"{int(m)} min {s:05.2f} s"


def imprimir_informe(m: dict, detalle: bool = False) -> None:
    N, (a, b) = m["n_piezas"], m["ventana"]
    cb = m["cuello_botella"]
    linea = "─" * 78

    print(f"\nDIAGRAMA O-T · BOLÍGRAF RETRÀCTIL — comanda de {N} peces")
    print(f"Règim calculat amb P{a} → P{b} ({b - a} intervals)"
          + ("" if m["regimen_estable"] else "   ⚠ el règim NO és estable en aquesta finestra"))
    print(linea)
    print(f"Termini de lliurament ({N} peces)  {m['termini_s']:>11.2f} s   = {_hms(m['termini_s'])}")
    print(f"Temps de cicle del procés         {m['ciclo_s']:>11.2f} s/peça"
          f"   (coll d'ampolla: {cb} · {OPERACIONES[cb][0]}, {OPERACIONES[cb][1]:.2f} s)")
    print(f"Capacitat                         {m['capacidad_h']:>11.2f} peces/h")
    print(f"Productivitat                     {m['productividad_h_recurso']:>11.2f} peces/h/recurs"
          f"   ({m['n_recursos']} recursos)")

    print(f"\nESTOC ENTRE OPERACIONS")
    print(f"{'':10}{'— règim (P%d→P%d) —' % (a, b):^28}{'— comanda (P0→P%d) —' % (N):^36}")
    print(f"{'Magatzem':10}{'espera/peça':>14}{'estoc mitjà':>14}{'espera màx':>12}{'estoc màx':>11}{'estoc mitjà':>13}")
    for e in m["estoc"]:
        print(f"{e['origen'] + ' → ' + e['destino']:10}{e['espera_pieza_regimen']:>12.2f} s"
              f"{e['estoc_medio_regimen']:>12.2f} p{e['espera_pieza_max']:>10.2f} s"
              f"{e['estoc_max']:>9d} p{e['estoc_medio_pedido']:>11.2f} p")

    print(f"\nESPERA DELS RECURSOS")
    print(f"{'Op':4}{'Recurs':22}{'t op':>8}{'espera/peça':>13}{'utilització':>13}"
          f"{'espera inicial':>16}{'espera total*':>15}")
    for r in m["esperas"]:
        print(f"{r['op']:4}{r['nombre']:22}{r['t_op']:>8.2f}{r['espera_por_pieza_regimen']:>11.2f} s"
              f"{r['utilizacion_regimen']:>12.1%}{r['espera_inicial']:>14.2f} s{r['espera_entre_piezas']:>13.2f} s")
    print("  espera/peça i utilització: règim · *espera total entre peces dins la comanda")

    print(f"\nPECES (entrada = inici de la primera operació, sortida = final de Q)")
    files = m["piezas"]
    if not detalle and len(files) > 12:
        mostrar = files[:5] + [None] + [f for f in files if f["pieza"] in (a, b)] + [None] + files[-2:]
        vistos, net = set(), []
        for f in mostrar:  # sin duplicados y conservando los separadores
            if f is None or f["pieza"] not in vistos:
                net.append(f)
                vistos.add(None if f is None else f["pieza"])
        mostrar = net
    else:
        mostrar = files
    print(f"{'Peça':>6}{'entrada (s)':>14}{'sortida (s)':>14}{'temps de pas (s)':>18}")
    for f in mostrar:
        if f is None:
            print(f"{'…':>6}")
            continue
        print(f"{'P' + str(f['pieza']):>6}{f['entrada']:>14.2f}{f['salida']:>14.2f}{f['paso']:>18.2f}")

    print(f"\nCOMPROVACIÓ DEL DIAGRAMA")
    if m["problemas"]:
        print(f"  ⚠ {len(m['problemas'])} conflictes:")
        for p in m["problemas"][:20]:
            print("   -", p)
    else:
        print("  Cap recurs fa dues peces alhora i cap operació comença abans que les seves entrades.")
    print()


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
