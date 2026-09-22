"""Calcula el Índice de Reputación (0 a 100) a partir del snapshot mensual y el censo.

  python3 pipeline/score.py [--periodo AAAA-MM] [--snapshot ruta] [--censo data/hospitales.json] [--config config.json]

Escribe data/ranking/AAAA-MM.json y actualiza data/historial.json.

Metodología (ver README):
  calificacion_ajustada = (n/(n+m))*calificacion + (m/(n+m))*C
      n = reseñas del hospital, m = mediana de reseñas del universo rankeado, C = promedio nacional ponderado
  puntaje_calificacion = (calificacion_ajustada - 1) / 4 * 100
  puntaje_volumen      = log10(n+1) / log10(n_max+1) * 100
  indice               = 75% puntaje_calificacion + 25% puntaje_volumen   (pesos en config.json)
"""
import argparse
import datetime as dt
import json
import math
import os
import statistics
import zoneinfo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = zoneinfo.ZoneInfo("America/Costa_Rica")
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def etiqueta(periodo: str) -> str:
    a, m = periodo.split("-")
    return f"Edición de {MESES[int(m) - 1]} de {a}"


def proxima_fecha(periodo: str, dia: int) -> str:
    a, m = (int(x) for x in periodo.split("-"))
    m += 1
    if m > 12:
        a, m = a + 1, 1
    return f"{a:04d}-{m:02d}-{dia:02d}"


def ranking_anterior(periodo: str):
    carpeta = os.path.join(RAIZ, "data", "ranking")
    previos = sorted(f[:-5] for f in os.listdir(carpeta) if f.endswith(".json") and f[:-5] < periodo and f[:4].isdigit())
    if not previos:
        return None
    return json.load(open(os.path.join(carpeta, previos[-1] + ".json"), encoding="utf-8"))


def redondear(x, nd=1):
    return None if x is None else round(x, nd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--periodo")
    ap.add_argument("--snapshot")
    ap.add_argument("--censo", default=os.path.join(RAIZ, "data", "hospitales.json"))
    ap.add_argument("--config", default=os.path.join(RAIZ, "config.json"))
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    periodo = args.periodo or dt.datetime.now(TZ).strftime("%Y-%m")
    snap_path = args.snapshot or os.path.join(RAIZ, "data", "snapshots", f"{periodo}.json")
    snap = json.load(open(snap_path, encoding="utf-8"))
    censo = {h["id"]: h for h in json.load(open(args.censo, encoding="utf-8"))}
    pesos = cfg.get("pesos", {"calificacion_ajustada": 0.75, "volumen": 0.25})
    minimo = int(cfg.get("minimo_resenas_para_ranking", 10))
    tipos = set(cfg.get("tipos_incluidos") or ["publico", "privado"])

    filas = []
    for s in snap["hospitales"]:
        c = censo.get(s["id"], {})
        if c.get("tipo") not in tipos:
            continue
        fila = {
            "id": s["id"], "cid": s.get("cid") or c.get("cid"),
            "nombre_google": s.get("nombre_google") or c.get("nombre_google"),
            "tipo": c.get("tipo"), "red": c.get("red"), "clasificacion": c.get("clasificacion"),
            "categoria_google": s.get("categoria_google"),
            "provincia": c.get("provincia"), "canton": c.get("canton"),
            "direccion": s.get("direccion"), "sitio_web": s.get("sitio_web") or c.get("sitio_web"),
            "telefono": s.get("telefono"), "maps_url": s.get("maps_url") or c.get("maps_url"),
            "calificacion": s.get("calificacion"), "resenas": s.get("resenas"),
            "distribucion": s.get("distribucion"), "pct_5": None, "pct_1": None,
            "calificacion_ajustada": None, "puntaje_calificacion": None, "puntaje_volumen": None, "indice": None,
            "posicion": None, "posicion_tipo": None, "posicion_anterior": None, "delta_posicion": None,
            "calificacion_anterior": None, "delta_calificacion": None, "resenas_anterior": None, "delta_resenas": None,
            "muestra_resenas": None, "en_ranking": False, "motivo_exclusion": None,
        }
        d = s.get("distribucion")
        if d and sum(d.values()) > 0:
            tot = sum(d.values())
            fila["pct_5"] = round(d.get("5", 0) / tot * 100, 1)
            fila["pct_1"] = round(d.get("1", 0) / tot * 100, 1)
        mr = s.get("muestra_resenas")
        if mr and mr.get("visibles"):
            fila["muestra_resenas"] = {**mr, "pct_respuesta": round(mr["con_respuesta"] / mr["visibles"] * 100, 1)}
        if s.get("error"):
            fila["motivo_exclusion"] = f"Sin datos este mes: {s['error']}"
        elif fila["calificacion"] is None or fila["resenas"] is None:
            fila["motivo_exclusion"] = "Google no mostró calificación o reseñas"
        elif fila["resenas"] < minimo:
            fila["motivo_exclusion"] = f"Menos de {minimo} reseñas ({fila['resenas']})"
        else:
            fila["en_ranking"] = True
        filas.append(fila)

    rank = [f for f in filas if f["en_ranking"]]
    if not rank:
        raise SystemExit("No hay hospitales con datos suficientes para rankear")
    m = statistics.median(f["resenas"] for f in rank)
    C = sum(f["calificacion"] * f["resenas"] for f in rank) / sum(f["resenas"] for f in rank)
    n_max = max(f["resenas"] for f in rank)
    for f in rank:
        n, r = f["resenas"], f["calificacion"]
        adj = (n / (n + m)) * r + (m / (n + m)) * C
        pc = max(0.0, min(100.0, (adj - 1) / 4 * 100))
        pv = math.log10(n + 1) / math.log10(n_max + 1) * 100
        f["calificacion_ajustada"] = round(adj, 3)
        f["puntaje_calificacion"] = round(pc, 1)
        f["puntaje_volumen"] = round(pv, 1)
        f["indice"] = round(pesos["calificacion_ajustada"] * pc + pesos["volumen"] * pv, 1)
    # desempate: índice, luego calificación ajustada, luego reseñas
    rank.sort(key=lambda f: (-f["indice"], -f["calificacion_ajustada"], -f["resenas"]))
    for i, f in enumerate(rank, 1):
        f["posicion"] = i
    for tipo in ("publico", "privado"):
        for i, f in enumerate([f for f in rank if f["tipo"] == tipo], 1):
            f["posicion_tipo"] = i

    ant = ranking_anterior(periodo)
    if ant:
        prev = {h["cid"]: h for h in ant["hospitales"] if h.get("cid")}
        for f in rank:
            p = prev.get(f["cid"])
            if p and p.get("en_ranking"):
                f["posicion_anterior"] = p["posicion"]
                f["delta_posicion"] = p["posicion"] - f["posicion"]
                f["calificacion_anterior"] = p["calificacion"]
                f["delta_calificacion"] = redondear(f["calificacion"] - p["calificacion"], 1)
                f["resenas_anterior"] = p["resenas"]
                f["delta_resenas"] = f["resenas"] - p["resenas"]

    orden = {f["id"]: i for i, f in enumerate(rank)}
    filas.sort(key=lambda f: (0, orden[f["id"]]) if f["en_ranking"] else (1, f["nombre_google"] or ""))
    salida = {
        "periodo": periodo, "etiqueta_periodo": etiqueta(periodo),
        "generado": dt.datetime.now(TZ).replace(microsecond=0).isoformat(),
        "capturado": snap.get("capturado"),
        "proxima_actualizacion": proxima_fecha(periodo, int(cfg.get("dia_actualizacion", 1))),
        "fuente": snap.get("fuente"),
        "universo": {
            "total": len(filas),
            "publicos": sum(1 for f in filas if f["tipo"] == "publico"),
            "privados": sum(1 for f in filas if f["tipo"] == "privado"),
            "sin_datos": sum(1 for f in filas if not f["en_ranking"]),
        },
        "parametros": {"m": round(m, 1), "C": round(C, 3), "pesos": pesos, "minimo_resenas": minimo, "tipos_incluidos": sorted(tipos)},
        "hospitales": filas,
    }
    out = os.path.join(RAIZ, "data", "ranking", f"{periodo}.json")
    json.dump(salida, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # historial
    hpath = os.path.join(RAIZ, "data", "historial.json")
    hist = json.load(open(hpath, encoding="utf-8")) if os.path.exists(hpath) else {"periodos": [], "hospitales": {}}
    if periodo not in hist["periodos"]:
        hist["periodos"].append(periodo)
        hist["periodos"].sort()
    for f in rank:
        if not f["cid"]:
            continue
        ent = hist["hospitales"].setdefault(f["cid"], {"nombre_google": f["nombre_google"], "serie": []})
        ent["nombre_google"] = f["nombre_google"]
        ent["serie"] = [p for p in ent["serie"] if p["periodo"] != periodo]
        ent["serie"].append({"periodo": periodo, "posicion": f["posicion"], "indice": f["indice"],
                             "calificacion": f["calificacion"], "resenas": f["resenas"]})
        ent["serie"].sort(key=lambda p: p["periodo"])
    json.dump(hist, open(hpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"Ranking {periodo}: {len(rank)} en ranking, {len(filas)-len(rank)} fuera. m={m:.0f}, C={C:.3f}. Salida: {out}")
    for f in rank[:5]:
        print(f"  {f['posicion']:>2}. {f['nombre_google']} ({f['tipo']}): {f['calificacion']} con {f['resenas']} reseñas, índice {f['indice']}")


if __name__ == "__main__":
    main()
