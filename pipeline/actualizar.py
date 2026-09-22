"""Corrida mensual completa: capturar fichas, calcular el índice y regenerar el sitio.

  python3 pipeline/actualizar.py [--periodo AAAA-MM] [--sin-captura]

Falla con código 1 si se leyeron menos del 80% de las fichas (para que GitHub Actions avise).
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import zoneinfo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
TZ = zoneinfo.ZoneInfo("America/Costa_Rica")


def correr(*cmd):
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=RAIZ)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--periodo", default=dt.datetime.now(TZ).strftime("%Y-%m"))
    ap.add_argument("--sin-captura", action="store_true", help="no vuelve a leer Google, solo recalcula y publica")
    ap.add_argument("--umbral", type=float, default=0.8)
    args = ap.parse_args()

    if not args.sin_captura:
        # Descubrimiento corto: refresca la lista de resultados (respaldo del total de reseñas) y detecta perfiles nuevos
        correr(PY, "pipeline/gmaps.py", "descubrir", "--consultas", "pipeline/consultas_mensuales.txt",
               "--salida", os.path.join("data", "raw", f"descubrimiento-{args.periodo}.json"))
        correr(PY, "pipeline/gmaps.py", "capturar", "--periodo", args.periodo)
    snap = json.load(open(os.path.join(RAIZ, "data", "snapshots", f"{args.periodo}.json"), encoding="utf-8"))
    total = len(snap["hospitales"])
    ok = sum(1 for h in snap["hospitales"] if h.get("error") is None)
    print(f"Fichas leídas: {ok}/{total}")
    if total == 0 or ok / total < args.umbral:
        sys.exit(f"Captura insuficiente ({ok}/{total}); no se publica el ranking de {args.periodo}")
    # Plausibilidad: calificación dentro de 1 a 5 y sin saltos raros de reseñas contra el mes anterior
    carpeta = os.path.join(RAIZ, "data", "snapshots")
    previos = sorted(f for f in os.listdir(carpeta) if f.endswith(".json") and f[:-5] < args.periodo)
    anterior = {}
    if previos:
        anterior = {h.get("cid"): h for h in json.load(open(os.path.join(carpeta, previos[-1]), encoding="utf-8"))["hospitales"] if h.get("cid")}
    sospechosos = []
    for h in snap["hospitales"]:
        if h.get("error"):
            continue
        cal, n = h.get("calificacion"), h.get("resenas")
        if cal is not None and not (1.0 <= cal <= 5.0):
            sospechosos.append(f"{h['id']}: calificación fuera de rango ({cal})")
        p = anterior.get(h.get("cid"))
        if p and p.get("resenas") and n is not None:
            if n < p["resenas"] * 0.7 or n > p["resenas"] * 1.6 + 20:
                sospechosos.append(f"{h['id']}: reseñas pasaron de {p['resenas']} a {n}")
            if p.get("calificacion") is not None and cal is not None and abs(cal - p["calificacion"]) >= 0.6:
                sospechosos.append(f"{h['id']}: calificación pasó de {p['calificacion']} a {cal}")
    for s in sospechosos:
        print("AVISO plausibilidad:", s)
    if ok and len(sospechosos) > ok * 0.25:
        sys.exit(f"Demasiados datos implausibles ({len(sospechosos)} de {ok}); revisar el extractor antes de publicar")
    correr(PY, "pipeline/score.py", "--periodo", args.periodo)
    correr(PY, "pipeline/build_site.py", "--out", "docs")
    print("Actualización completa.")


if __name__ == "__main__":
    main()
