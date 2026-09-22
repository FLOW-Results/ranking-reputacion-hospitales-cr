"""Cruza el censo de candidatos (data/censo_candidatos.json) con lo descubierto en Google Maps
(data/raw/descubrimiento-*.json) y escribe data/hospitales.json (la lista blanca del ranking).

  python3 pipeline/cruzar_censo.py [--descubrimiento ruta] [--censo data/censo_candidatos.json]

Reporta: coincidencias, candidatos del censo sin perfil (se buscan por nombre en la captura) y
perfiles de Google con categoría de hospital que NO están en el censo (para revisión humana).
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gmaps import normalizar  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATS_HOSPITAL = {"hospital", "hospital privado", "hospital general", "hospital infantil", "hospital universitario",
                 "hospital psiquiátrico", "hospital especializado", "hospital de la mujer", "hospital público",
                 "hospital militar", "hospital geriátrico", "centro de rehabilitación", "hospital de maternidad",
                 "hospital de veteranos", "servicio de urgencias"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--descubrimiento")
    ap.add_argument("--censo", default=os.path.join(RAIZ, "data", "censo_candidatos.json"))
    ap.add_argument("--salida", default=os.path.join(RAIZ, "data", "hospitales.json"))
    args = ap.parse_args()
    desc_path = args.descubrimiento or sorted(glob.glob(os.path.join(RAIZ, "data", "raw", "descubrimiento-*.json")))[-1]
    desc = json.load(open(desc_path, encoding="utf-8"))["resultados"]
    censo = json.load(open(args.censo, encoding="utf-8"))
    cand = censo["hospitales"] if isinstance(censo, dict) else censo

    indice = {}
    for r in desc:
        if r.get("cid"):
            indice.setdefault(normalizar(r["nombre_google"]), []).append(r)

    salida, sin_perfil, usados = [], [], set()
    for h in cand:
        nombres = [h.get("nombre_oficial") or h.get("nombre_google")] + list(h.get("alias") or [])
        match = None
        if h.get("cid"):  # el censo ya fija el perfil de Google: se respeta
            match = next((r for r in desc if r.get("cid") == h["cid"]), None) or {
                "cid": h["cid"], "maps_url": h.get("maps_url"), "nombre_google": h.get("nombre_google") or nombres[0]}
        if h.get("buscar_por_nombre"):  # el cruce automático confunde este nombre: la captura lo busca por nombre
            nombres = []
        for n in ([] if match else nombres):
            k = normalizar(n)
            if k in indice:
                cands = indice[k]
                # si hay varias sedes con el mismo nombre, preferir la que mencione el cantón en la dirección
                canton = normalizar(h.get("canton", ""))
                match = next((c for c in cands if canton and canton in normalizar(c.get("direccion") or "")), cands[0])
                break
        if not match and not h.get("cid") and not h.get("buscar_por_nombre"):  # coincidencia parcial: todas las palabras del censo dentro del nombre de Google
            for n in nombres:
                palabras = set(normalizar(n).split())
                if not palabras:
                    continue
                for k, cands in indice.items():
                    if palabras <= set(k.split()) and cands[0]["cid"] not in usados:
                        match = cands[0]
                        break
                if match:
                    break
        fila = {
            "id": h["id"], "nombre_google": match["nombre_google"] if match else (h.get("nombre_oficial") or h.get("nombre_google")),
            "nombre_oficial": h.get("nombre_oficial"), "alias": h.get("alias", []),
            "tipo": h["tipo"], "red": h.get("red"), "clasificacion": h.get("clasificacion"),
            "provincia": h.get("provincia"), "canton": h.get("canton"),
            "sitio_web": (match or {}).get("sitio_web") or h.get("sitio_web"),
            "maps_url": (match.get("maps_url") if match else None) or h.get("maps_url"), "cid": match["cid"] if match else None,
            "categoria_google": (match or {}).get("categoria_google"),
            "fuentes": h.get("fuentes", []), "confianza": h.get("confianza"), "notas": h.get("notas", ""),
        }
        if match:
            usados.add(match["cid"])
        else:
            sin_perfil.append(h["id"])
        salida.append(fila)

    # perfiles de Google con pinta de hospital que no están en el censo
    no_censados = [r for r in desc if r.get("cid") and r["cid"] not in usados
                   and (r.get("categoria_google") or "").lower() in CATS_HOSPITAL
                   and "hospital" in (r.get("nombre_google") or "").lower()]
    json.dump(salida, open(args.salida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rev = os.path.join(RAIZ, "data", "raw", "perfiles_no_censados.json")
    json.dump(no_censados, open(rev, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Censo: {len(cand)} candidatos. Con perfil de Google: {len(cand)-len(sin_perfil)}. Sin perfil (se buscarán por nombre): {len(sin_perfil)}")
    for s in sin_perfil:
        print("   sin perfil:", s)
    print(f"Perfiles de Google tipo hospital fuera del censo: {len(no_censados)} (ver {rev})")
    for r in no_censados:
        print(f"   revisar: {r['nombre_google']} [{r.get('categoria_google')}] {r.get('calificacion')} ({r.get('resenas')}) {r.get('direccion')}")


if __name__ == "__main__":
    main()
