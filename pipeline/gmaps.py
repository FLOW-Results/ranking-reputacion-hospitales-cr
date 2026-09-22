"""Lectura de perfiles de Google Business Profile (Google Maps) vía Firecrawl.

Dos operaciones:
  descubrir  : corre búsquedas de Google Maps ("hospitales en Cartago") y devuelve
               cada resultado con nombre, cid, calificación, reseñas, categoría, dirección, web.
  capturar   : lee la ficha de cada hospital del censo (data/hospitales.json) y escribe
               el snapshot mensual data/snapshots/AAAA-MM.json.

Uso:
  python3 pipeline/gmaps.py descubrir [--consultas archivo.txt] [--salida data/raw/descubrimiento-AAAA-MM.json]
  python3 pipeline/gmaps.py capturar [--censo data/hospitales.json] [--periodo AAAA-MM] [--solo id1,id2] [--hilos 4]
  python3 pipeline/gmaps.py ficha "URL de Maps"        (prueba de una sola ficha)
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import zoneinfo
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fc import scrape  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = zoneinfo.ZoneInfo("America/Costa_Rica")
RE_CID = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)")
FUENTE = "Google Business Profile (Google Maps) vía Firecrawl"


def ahora_iso() -> str:
    return dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def periodo_actual() -> str:
    return dt.datetime.now(TZ).strftime("%Y-%m")


def num_es(texto: str):
    """'3,4' -> 3.4 ; '2.001' -> 2001 ; '377' -> 377."""
    if texto is None:
        return None
    t = texto.strip().replace("\xa0", "").replace(" ", "")
    if re.fullmatch(r"\d+,\d+", t):
        return float(t.replace(",", "."))
    t = t.replace(".", "").replace(",", "")
    return int(t) if t.isdigit() else None


def normalizar(nombre: str) -> str:
    """Clave de comparación de nombres: minúsculas, sin tildes ni puntuación ni palabras vacías."""
    s = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    vacias = {"hospital", "dr", "dra", "doctor", "de", "del", "la", "el", "los", "las", "y", "the", "san", "clinica"}
    return " ".join(w for w in s.split() if w not in vacias)


def limpiar_url_maps(url: str) -> str:
    """Quita parámetros volátiles y deja la URL de la ficha estable."""
    if not url:
        return url
    return url.split("?")[0] + "?hl=es"


# ---------- Lista de resultados ----------
def parsear_lista(html: str) -> list:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for cont in soup.select("div.Nv2PK"):
        a = cont.select_one("a.hfpxzc")
        if not a:
            continue
        href = a.get("href", "")
        m = RE_CID.search(href)
        est = cont.select_one("span.ZkP5Je")
        cal = res = None
        if est and est.get("aria-label"):
            mm = re.search(r"([\d,]+) estrellas\s+([\d.]+) reseñas", est["aria-label"])
            if mm:
                cal, res = num_es(mm.group(1)), num_es(mm.group(2))
        if cal is None:  # segundo diseño o carga parcial: calificación y total en spans separados
            r1, r2 = cont.select_one("span.MW4etd"), cont.select_one("span.UY7F9")
            if r1:
                cal = num_es(r1.get_text())
            if r2:
                res = num_es(r2.get_text().strip("()"))
        categoria = direccion = None
        for d in cont.select("div.W4Efsd"):
            ln = d.get_text(" ", strip=True).replace("", "")
            partes = [p.strip() for p in re.split(r"\s*·\s*", ln) if p.strip()]
            if not partes or re.match(r"^[\d,]+(\s*\(.*)?$", partes[0]) or partes[0].startswith(("Abierto", "Cerrado", "Abre", "Cierra", "No hay reseñas")):
                continue
            categoria = partes[0]
            direccion = partes[1] if len(partes) > 1 else None
            break
        web = cont.select_one("a.lcr4fd")
        out.append({
            "nombre_google": a.get("aria-label", "").strip(),
            "cid": m.group(1) if m else None,
            "maps_url": limpiar_url_maps(href),
            "calificacion": cal,
            "resenas": res,
            "categoria_google": categoria,
            "direccion": direccion,
            "sitio_web": web.get("href") if web else None,
        })
    return out


def url_busqueda(consulta: str) -> str:
    return "https://www.google.com/maps/search/" + urllib.parse.quote(consulta) + "/?hl=es"


def buscar(consulta: str, wait_for: int = 6000) -> list:
    d = scrape(url_busqueda(consulta), formats=["html"], wait_for=wait_for)
    if "error" in d:
        return [{"error": d["error"], "consulta": consulta}]
    html = d.get("html", "")
    filas = parsear_lista(html)
    if filas and any(f["calificacion"] is not None and f["resenas"] is None for f in filas) and wait_for < 9000:
        # carga parcial (calificación sin total): una segunda lectura con más espera
        d2 = scrape(url_busqueda(consulta), formats=["html"], wait_for=9000)
        if "error" not in d2:
            filas2 = parsear_lista(d2.get("html", ""))
            if filas2 and sum(f["resenas"] is not None for f in filas2) >= sum(f["resenas"] is not None for f in filas):
                html, filas = d2.get("html", ""), filas2
    if not filas:
        # Con una sola coincidencia fuerte, Maps salta directo a la ficha: la URL final trae el cid.
        f = parsear_ficha(html)
        meta = d.get("metadata") or {}
        url_final = meta.get("url") or meta.get("sourceURL") or ""
        m = RE_CID.search(url_final)
        if f.get("nombre_google") and m:
            filas = [{
                "nombre_google": f["nombre_google"], "cid": m.group(1), "maps_url": limpiar_url_maps(url_final),
                "calificacion": f.get("calificacion"), "resenas": f.get("resenas"),
                "categoria_google": f.get("categoria_google"), "direccion": f.get("direccion"),
                "sitio_web": f.get("sitio_web"), "ficha_directa": True,
            }]
    for f in filas:
        f["consulta"] = consulta
    return filas


# ---------- Ficha ----------
def parsear_ficha(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.h1.get_text(strip=True) if soup.h1 else None
    cal = res = None
    for s in soup.select("div.F7nice span[aria-label]"):
        lab = s["aria-label"].strip()
        m1 = re.fullmatch(r"([\d,]+) estrellas", lab)
        m2 = re.fullmatch(r"([\d.\xa0]+) reseñas?", lab)
        if m1 and cal is None:
            cal = num_es(m1.group(1))
        if m2 and res is None:
            res = num_es(m2.group(1))
    dist = {}
    for tr in soup.select("tr[aria-label]"):
        m = re.fullmatch(r"(\d) estrellas?,\s*([\d.]+) reseñas?", tr["aria-label"].strip())
        if m:
            dist[m.group(1)] = num_es(m.group(2))
    if len(dist) != 5:
        dist = None
    cat = soup.select_one("button.DkEaL")
    dire = soup.select_one('button[aria-label^="Dirección"]')
    tel = soup.select_one('button[aria-label^="Teléfono"]')
    web = soup.select_one('a[aria-label^="Sitio web"]')
    revs = soup.select("div.jftiEf")
    muestra = None
    if revs:
        muestra = {"visibles": len(revs),
                   "con_respuesta": sum(1 for r in revs if "Respuesta del propietario" in r.get_text())}
    return {
        "nombre_google": h1,
        "calificacion": cal,
        "resenas": res,
        "distribucion": dist,
        "categoria_google": cat.get_text(strip=True) if cat else None,
        "direccion": dire["aria-label"].split(":", 1)[1].strip() if dire else None,
        "telefono": tel["aria-label"].split(":", 1)[1].strip() if tel else None,
        "sitio_web": web.get("href") if web else None,
        "muestra_resenas": muestra,
    }


def leer_ficha(maps_url: str, nombre_pista: str = None, canton_pista: str = "", cid: str = None, intentos: int = 3) -> dict:
    """Lee la ficha; reintenta con más espera si Google no pintó calificación o total de reseñas.
    Si aun así falta el total, lo suma de la distribución o lo toma de una búsqueda por nombre."""
    mejor, ultimo = None, None
    for i in range(intentos):
        d = scrape(maps_url, formats=["html"], wait_for=6000 + 3000 * i)
        if "error" in d:
            ultimo = d["error"]
            continue
        f = parsear_ficha(d.get("html", ""))
        if not f["nombre_google"]:
            ultimo = "ficha sin nombre (Google no mostró el panel)"
            continue
        if mejor is None or (f["resenas"] is not None and mejor.get("resenas") is None) \
                or (f["distribucion"] and not mejor.get("distribucion")):
            mejor = f
        if f["calificacion"] is not None and f["resenas"] is not None:
            break
    if mejor is None:
        return {"error": ultimo or "sin respuesta"}
    mejor["fuente_total"] = "ficha"
    if mejor["resenas"] is None and mejor.get("distribucion"):
        mejor["resenas"] = sum(mejor["distribucion"].values())
        mejor["fuente_total"] = "suma de distribución"
    if (mejor["resenas"] is None or mejor["calificacion"] is None) and nombre_pista:
        for r in buscar(f"{nombre_pista} {canton_pista} Costa Rica".strip()):
            if "error" in r:
                break
            if (cid and r.get("cid") == cid) or normalizar(r["nombre_google"]) == normalizar(mejor["nombre_google"]):
                if r.get("resenas") is not None:
                    mejor["resenas"] = r["resenas"]
                    if mejor["calificacion"] is None:
                        mejor["calificacion"] = r.get("calificacion")
                    mejor["fuente_total"] = "búsqueda por nombre"
                break
    ok = mejor["calificacion"] is not None and mejor["resenas"] is not None
    mejor["error"] = None if ok else "Google no mostró calificación o total de reseñas"
    return mejor


def ficha_por_nombre(nombre: str, pista: str = ""):
    """Busca el perfil por nombre y devuelve el primer resultado cuyo nombre normalizado coincide."""
    objetivo = normalizar(nombre)
    filas = buscar(f"{nombre} {pista} Costa Rica".strip())
    for f in filas:
        if "error" in f:
            return None
        if normalizar(f["nombre_google"]) == objetivo or objetivo in normalizar(f["nombre_google"]):
            return f
    return filas[0] if filas and "error" not in filas[0] else None


# ---------- Operaciones ----------
def op_descubrir(args):
    if args.consultas:
        consultas = [l.strip() for l in open(args.consultas, encoding="utf-8") if l.strip() and not l.startswith("#")]
    else:
        consultas = CONSULTAS_BASE
    salida = args.salida or os.path.join(RAIZ, "data", "raw", f"descubrimiento-{periodo_actual()}.json")
    vistos, errores = {}, []
    if args.acumular and os.path.exists(salida):
        for f in json.load(open(salida, encoding="utf-8")).get("resultados", []):
            vistos[f.get("cid") or normalizar(f["nombre_google"])] = f
    t0 = time.time()
    for i, c in enumerate(consultas, 1):
        res = buscar(c)
        nuevos = 0
        for f in res:
            if "error" in f:
                errores.append(f)
                continue
            k = f["cid"] or normalizar(f["nombre_google"])
            if k not in vistos:
                vistos[k] = f
                nuevos += 1
            elif f.get("resenas") is not None and vistos[k].get("resenas") is None:
                vistos[k] = f  # versión más completa del mismo perfil
        print(f"[{i}/{len(consultas)}] {c}: {len(res)} resultados, {nuevos} nuevos, acumulado {len(vistos)}", flush=True)
        json.dump({"generado": ahora_iso(), "consultas": consultas, "errores": errores, "resultados": list(vistos.values())},
                  open(salida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Listo: {len(vistos)} perfiles únicos en {salida} ({time.time()-t0:.0f}s, {len(errores)} errores)")


def cargar_respaldo() -> dict:
    """Último archivo de descubrimiento, indexado por cid: la lista de resultados siempre trae el total."""
    import glob
    archivos = sorted(glob.glob(os.path.join(RAIZ, "data", "raw", "descubrimiento-*.json")))
    if not archivos:
        return {}
    filas = json.load(open(archivos[-1], encoding="utf-8")).get("resultados", [])
    return {f["cid"]: f for f in filas if f.get("cid")}


def capturar_uno(h: dict, respaldo: dict = None) -> dict:
    respaldo = respaldo or {}
    fila = {"id": h["id"], "cid": h.get("cid"), "maps_url": h.get("maps_url")}
    nombre = h.get("nombre_google") or h.get("nombre_oficial")
    maps_url = h.get("maps_url")
    if not maps_url:
        enc = ficha_por_nombre(nombre, h.get("canton", ""))
        if enc:
            maps_url = enc["maps_url"]
            fila["cid"] = fila["cid"] or enc.get("cid")
            fila["maps_url"] = maps_url
    if not maps_url:
        fila["error"] = "no se encontró el perfil en Google Maps"
    else:
        fila.update(leer_ficha(maps_url, nombre_pista=nombre, canton_pista=h.get("canton", ""), cid=fila.get("cid")))
        if not fila.get("cid"):
            m = RE_CID.search(maps_url)
            fila["cid"] = m.group(1) if m else None
        r = respaldo.get(fila.get("cid"))
        if r and (fila.get("resenas") is None or fila.get("calificacion") is None) and r.get("resenas") is not None:
            fila["resenas"] = r["resenas"]
            if fila.get("calificacion") is None:
                fila["calificacion"] = r.get("calificacion")
            fila["nombre_google"] = fila.get("nombre_google") or r.get("nombre_google")
            fila["categoria_google"] = fila.get("categoria_google") or r.get("categoria_google")
            fila["fuente_total"] = "lista de resultados (descubrimiento)"
            fila["error"] = None if (fila["calificacion"] is not None and fila["resenas"] is not None) else fila.get("error")
    fila["capturado"] = ahora_iso()
    return fila


def op_capturar(args):
    censo = json.load(open(args.censo, encoding="utf-8"))
    periodo = args.periodo or periodo_actual()
    solo = set(args.solo.split(",")) if args.solo else None
    salida = os.path.join(RAIZ, "data", "snapshots", f"{periodo}.json")
    previo = {}
    if os.path.exists(salida) and not args.reiniciar:
        previo = {h["id"]: h for h in json.load(open(salida, encoding="utf-8")).get("hospitales", [])}
    resultados, pendientes = {}, []
    for h in censo:
        conservar = h["id"] in previo and previo[h["id"]].get("error") is None
        if solo:
            if h["id"] in solo:
                pendientes.append(h)
            elif h["id"] in previo:
                resultados[h["id"]] = previo[h["id"]]
        elif conservar:
            resultados[h["id"]] = previo[h["id"]]
        else:
            pendientes.append(h)
    print(f"Fichas a leer: {len(pendientes)} de {len(censo)} (conservadas del snapshot: {len(resultados)})", flush=True)

    def guardar():
        orden = [resultados[h["id"]] for h in censo if h["id"] in resultados]
        json.dump({"periodo": periodo, "capturado": ahora_iso(), "fuente": FUENTE, "hospitales": orden},
                  open(salida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    respaldo = cargar_respaldo()
    print(f"Respaldo de descubrimiento: {len(respaldo)} perfiles", flush=True)
    t0, hechos = time.time(), 0
    with ThreadPoolExecutor(max_workers=args.hilos) as ex:
        futuros = {ex.submit(capturar_uno, h, respaldo): h for h in pendientes}
        for fut in as_completed(futuros):
            h = futuros[fut]
            try:
                fila = fut.result()
            except Exception as e:  # nunca tumbar la corrida por un hospital
                fila = {"id": h["id"], "cid": h.get("cid"), "maps_url": h.get("maps_url"), "error": repr(e), "capturado": ahora_iso()}
            resultados[h["id"]] = fila
            hechos += 1
            est = fila.get("error") or f"{fila.get('calificacion')} ({fila.get('resenas')} reseñas, {fila.get('fuente_total')})"
            print(f"[{hechos}/{len(pendientes)}] {h['id']}: {est}", flush=True)
            if hechos % 5 == 0:
                guardar()
    guardar()
    ok = sum(1 for r in resultados.values() if r.get("error") is None)
    print(f"Listo: {ok}/{len(resultados)} fichas leídas en {time.time()-t0:.0f}s. Snapshot: {salida}")


CONSULTAS_BASE = [
    "hospitales en San José, Costa Rica", "hospitales en Alajuela, Costa Rica", "hospitales en Cartago, Costa Rica",
    "hospitales en Heredia, Costa Rica", "hospitales en Guanacaste, Costa Rica", "hospitales en Puntarenas, Costa Rica",
    "hospitales en Limón, Costa Rica",
    "hospital privado San José Costa Rica", "hospital privado Escazú", "hospital privado Santa Ana Costa Rica",
    "hospital privado Heredia Costa Rica", "hospital privado Alajuela Costa Rica", "hospital privado Cartago Costa Rica",
    "hospital privado Guanacaste", "hospital privado Liberia Costa Rica", "hospital privado Limón Costa Rica",
    "hospital privado Puntarenas Costa Rica", "hospital privado San Carlos Costa Rica", "hospital privado Pérez Zeledón",
    "hospital CCSS Guanacaste", "hospital CCSS Puntarenas", "hospital CCSS Limón", "hospital CCSS Alajuela",
    "hospital Nicoya Costa Rica", "hospital Guápiles Costa Rica", "hospital Turrialba Costa Rica", "hospital San Ramón Alajuela",
    "hospital Grecia Costa Rica", "hospital Quepos Costa Rica", "hospital Ciudad Neily Costa Rica", "hospital Golfito Costa Rica",
    "hospital Ciudad Cortés Osa Costa Rica", "hospital Upala Costa Rica", "hospital Los Chiles Costa Rica", "hospital San Vito Coto Brus",
    "hospital San Isidro de El General", "hospital Liberia Guanacaste", "hospital Puntarenas centro", "hospital Limón centro",
    "hospital Ciudad Quesada San Carlos", "hospital Tibás Costa Rica", "hospital Guadalupe Goicoechea Costa Rica",
    "hospital Desamparados Costa Rica", "hospital Curridabat Costa Rica", "hospital Lindora Santa Ana", "hospital Huacas Guanacaste",
    "hospital psiquiátrico Costa Rica", "hospital geriátrico Costa Rica", "hospital de niños Costa Rica", "hospital de la mujer Costa Rica",
    "hospital del trauma INS Costa Rica", "centro nacional de rehabilitación CENARE",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="op", required=True)
    d = sub.add_parser("descubrir")
    d.add_argument("--consultas"); d.add_argument("--salida"); d.add_argument("--acumular", action="store_true")
    c = sub.add_parser("capturar")
    c.add_argument("--censo", default=os.path.join(RAIZ, "data", "hospitales.json"))
    c.add_argument("--periodo"); c.add_argument("--solo"); c.add_argument("--reiniciar", action="store_true")
    c.add_argument("--hilos", type=int, default=4)
    f = sub.add_parser("ficha"); f.add_argument("url")
    args = ap.parse_args()
    if args.op == "descubrir":
        op_descubrir(args)
    elif args.op == "capturar":
        op_capturar(args)
    else:
        print(json.dumps(leer_ficha(args.url), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
