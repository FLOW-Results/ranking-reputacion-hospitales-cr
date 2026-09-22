#!/usr/bin/env python3
"""Genera el sitio estático del Ranking de Reputación Hospitalaria de Costa Rica.

Lee un archivo `data/ranking/AAAA-MM.json` (más `data/historial.json` y
`config.json`) y renderiza `pipeline/templates/index.html.j2` con Jinja2 hacia
`docs/index.html`, junto con las copias de datos abiertos en `docs/data/`.

Uso típico:
    python3 pipeline/build_site.py
    python3 pipeline/build_site.py --ranking data/ranking/fixture.json --historial data/historial.fixture.json --out docs

No depende de nada fuera de la carpeta `data/` (solo lectura) y no toca
`pipeline/fc.py`. Contrato de datos completo en `data/ESQUEMA.md`.
"""
import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

PIPELINE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PIPELINE_DIR / "templates"

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
MESES_ABR_ES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}

CSV_COLUMNAS = [
    "posicion", "posicion_tipo", "nombre_google", "tipo", "red", "clasificacion",
    "provincia", "canton", "calificacion", "resenas", "pct_5", "pct_1",
    "calificacion_ajustada", "indice", "delta_posicion", "delta_resenas",
    "maps_url", "sitio_web",
]


# ---------------------------------------------------------------------------
# Utilidades de formato (español de Costa Rica: miles con coma, decimales con
# punto; fechas largas en español). Nunca usan guion largo ni barra vertical.
# ---------------------------------------------------------------------------

def fmt_num(valor, decimales=0):
    """2001 -> '2,001'; 4.6 -> '4.6'. None -> 'N/D'."""
    if valor is None or isinstance(valor, bool):
        return "N/D"
    try:
        return f"{float(valor):,.{decimales}f}"
    except (TypeError, ValueError):
        return str(valor)


def fmt_delta(valor, decimales=0):
    """40 -> '+40'; -1 -> '-1'; 0 -> '0'; None -> None (no se muestra)."""
    if valor is None:
        return None
    numero = fmt_num(abs(valor), decimales)
    if valor > 0:
        return f"+{numero}"
    if valor < 0:
        return f"-{numero}"
    return "0"


def fmt_fecha_larga(valor):
    """'2026-09-21T22:40:00-06:00' o '2026-10-01' -> '21 de septiembre de 2026'."""
    if not valor:
        return "N/D"
    try:
        dt = datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        return str(valor)
    return f"{dt.day} de {MESES_ES[dt.month - 1]} de {dt.year}"


def etiqueta_periodo_corta(periodo):
    """'2026-09' -> 'sep 2026'."""
    try:
        anio, mes = periodo.split("-")
        return f"{MESES_ABR_ES[int(mes)]} {anio}"
    except (ValueError, KeyError, AttributeError):
        return periodo or ""


def limpiar_texto(valor):
    """Quita guion largo y barra vertical de cualquier texto libre que venga de los datos."""
    if not isinstance(valor, str):
        return valor
    texto = valor.replace("—", ", ").replace("|", ",")
    return re.sub(r"\s{2,}", " ", texto).strip()


def redondear_pct(fraccion):
    """0.75 -> '75'."""
    if fraccion is None:
        return "N/D"
    try:
        return str(int(round(float(fraccion) * 100)))
    except (TypeError, ValueError):
        return "N/D"


# ---------------------------------------------------------------------------
# Acceso seguro a datos que pueden venir null en cualquier punto.
# ---------------------------------------------------------------------------

def contar_estrellas(calificacion):
    """Redondea una calificación 0-5 al entero más cercano de estrellas llenas."""
    if not isinstance(calificacion, (int, float)) or isinstance(calificacion, bool):
        return 0
    return max(0, min(5, int(calificacion + 0.5)))


def etiqueta_tipo(h):
    if h.get("tipo") == "publico":
        red = h.get("red")
        return f"Público ({red})" if red else "Público"
    if h.get("tipo") == "privado":
        return "Privado"
    return "Sin clasificar"


def clasificar_cambio(h):
    """Determina si el hospital subió, bajó, quedó igual o es nuevo en el ranking."""
    anterior = h.get("posicion_anterior")
    delta = h.get("delta_posicion")
    if anterior is None:
        return {"tipo": "nuevo", "valor": None}
    if not isinstance(delta, (int, float)):
        return {"tipo": "igual", "valor": None}
    if delta > 0:
        return {"tipo": "subio", "valor": delta}
    if delta < 0:
        return {"tipo": "bajo", "valor": abs(delta)}
    return {"tipo": "igual", "valor": None}


def construir_distribucion(h):
    """Filas listas para pintar barras de 5 a 1 estrellas, o None si no hay dato."""
    dist = h.get("distribucion")
    if not dist:
        return None
    total = sum(v for v in dist.values() if isinstance(v, (int, float)))
    filas = []
    for estrella in ("5", "4", "3", "2", "1"):
        cantidad = dist.get(estrella)
        if not isinstance(cantidad, (int, float)):
            cantidad = 0
        pct = round((cantidad / total * 100), 1) if total else 0
        filas.append({"estrellas": int(estrella), "cantidad": cantidad, "cantidad_fmt": fmt_num(cantidad, 0), "pct": pct})
    return filas


def construir_nota_respuesta(h):
    muestra = h.get("muestra_resenas")
    if not muestra:
        return None
    visibles = muestra.get("visibles")
    con_respuesta = muestra.get("con_respuesta")
    if not isinstance(visibles, (int, float)) or not isinstance(con_respuesta, (int, float)):
        return None
    return f"Responde reseñas: {int(con_respuesta)} de {int(visibles)} visibles."


def construir_sparkline(serie, campo, invertir=False, ancho=100, alto=28, color="#123B6D", periodos=None):
    """Devuelve un <svg> de línea simple con la serie de `campo`, o None si hay menos de 2 valores.
    Cada punto se ubica según su periodo real dentro de `periodos` (lista global de meses), así un mes
    sin dato deja un hueco visible en vez de pegar los puntos."""
    periodos = list(periodos or [p.get("periodo") for p in serie])
    indice_periodo = {per: i for i, per in enumerate(periodos)}
    puntos_validos = [(indice_periodo.get(p.get("periodo"), i), p.get(campo)) for i, p in enumerate(serie)
                      if isinstance(p.get(campo), (int, float))]
    if len(puntos_validos) < 2:
        return None
    valores = [v for _, v in puntos_validos]
    minimo, maximo = min(valores), max(valores)
    rango = (maximo - minimo) or 1
    n = len(periodos)
    paso = ancho / (n - 1) if n > 1 else 0
    coords = []
    for i, valor in puntos_validos:
        x = i * paso
        frac = (valor - minimo) / rango
        if invertir:
            frac = 1 - frac
        y = alto - (frac * (alto - 6)) - 3
        coords.append((x, y))
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    circulos = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2" fill="{color}"></circle>' for x, y in coords)
    etiqueta = f"Serie de {len(coords)} periodos, de {fmt_num(valores[0], 1)} a {fmt_num(valores[-1], 1)}"
    return (
        f'<svg viewBox="0 0 {ancho} {alto}" width="{ancho}" height="{alto}" '
        f'class="sparkline" role="img" aria-label="{etiqueta}">'
        f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="1.5" '
        f'stroke-linejoin="round" stroke-linecap="round"></polyline>{circulos}</svg>'
    )


def construir_tendencias(cid, historial):
    """Sparklines de índice y puesto para un hospital, o None si no hay historial suficiente."""
    if not historial or not cid:
        return None
    registro = (historial.get("hospitales") or {}).get(cid)
    if not registro:
        return None
    serie = [p for p in (registro.get("serie") or []) if p.get("periodo")]
    if len(serie) < 2:
        return None
    serie = sorted(serie, key=lambda p: p["periodo"])
    periodos = historial.get("periodos") or [p["periodo"] for p in serie]
    svg_indice = construir_sparkline(serie, "indice", invertir=False, periodos=periodos)
    svg_posicion = construir_sparkline(serie, "posicion", invertir=True, periodos=periodos)
    if not svg_indice and not svg_posicion:
        return None
    return {
        "indice_svg": Markup(svg_indice) if svg_indice else None,
        "posicion_svg": Markup(svg_posicion) if svg_posicion else None,
        "desde": etiqueta_periodo_corta(serie[0]["periodo"]),
        "hasta": etiqueta_periodo_corta(serie[-1]["periodo"]),
        "cantidad": len(serie),
    }


# ---------------------------------------------------------------------------
# Preparación de cada hospital para la plantilla.
# ---------------------------------------------------------------------------

def nombre_para_mostrar(h, repetidos):
    """Nombre tal como lo muestra Google; si varios perfiles comparten nombre, se distingue por cantón."""
    nombre = limpiar_texto(h.get("nombre_google")) or "(sin nombre)"
    if repetidos.get(nombre, 0) > 1 and h.get("canton"):
        return f"{nombre} ({limpiar_texto(h.get('canton'))})"
    return nombre


def preparar_hospital(h, historial, repetidos=None):
    indice = h.get("indice")
    indice_bar = max(0, min(100, indice)) if isinstance(indice, (int, float)) else 0
    return {
        "id": h.get("id") or "",
        "cid": h.get("cid"),
        "nombre_google": nombre_para_mostrar(h, repetidos or {}),
        "grupo": limpiar_texto(h.get("grupo")) if h.get("grupo") else None,
        "tipo": h.get("tipo") or "",
        "tipo_label": etiqueta_tipo(h),
        "red": h.get("red"),
        "clasificacion": h.get("clasificacion"),
        "provincia": limpiar_texto(h.get("provincia")) or "N/D",
        "canton": limpiar_texto(h.get("canton")) or "N/D",
        "direccion": limpiar_texto(h.get("direccion")),
        "telefono": h.get("telefono"),
        "sitio_web": h.get("sitio_web"),
        "maps_url": h.get("maps_url"),
        "posicion": h.get("posicion"),
        "posicion_tipo": h.get("posicion_tipo"),
        "cambio": clasificar_cambio(h),
        "calificacion": h.get("calificacion"),
        "calificacion_fmt": fmt_num(h.get("calificacion"), 1),
        "estrellas": contar_estrellas(h.get("calificacion")),
        "resenas": h.get("resenas"),
        "resenas_fmt": fmt_num(h.get("resenas"), 0),
        "delta_resenas_fmt": fmt_delta(h.get("delta_resenas"), 0),
        "pct_5": h.get("pct_5"),
        "pct_5_fmt": fmt_num(h.get("pct_5"), 1),
        "pct_1": h.get("pct_1"),
        "pct_1_fmt": fmt_num(h.get("pct_1"), 1),
        "calificacion_ajustada": h.get("calificacion_ajustada"),
        "calificacion_ajustada_fmt": fmt_num(h.get("calificacion_ajustada"), 2),
        "puntaje_calificacion_fmt": fmt_num(h.get("puntaje_calificacion"), 1),
        "puntaje_volumen_fmt": fmt_num(h.get("puntaje_volumen"), 1),
        "indice": indice,
        "indice_fmt": fmt_num(indice, 1),
        "indice_bar_pct": indice_bar,
        "distribucion": construir_distribucion(h),
        "nota_respuesta": construir_nota_respuesta(h),
        "tendencias": construir_tendencias(h.get("cid"), historial),
    }


def preparar_hospital_fuera(h, historial=None):
    ultima = None
    registro = ((historial or {}).get("hospitales") or {}).get(h.get("cid")) if h.get("cid") else None
    if registro:
        puntos = [p for p in (registro.get("serie") or []) if p.get("posicion") is not None]
        if puntos:
            p = sorted(puntos, key=lambda x: x["periodo"])[-1]
            ultima = f"Última posición conocida: puesto {p['posicion']} en {etiqueta_periodo_corta(p['periodo'])}."
    return {
        "nombre_google": limpiar_texto(h.get("nombre_google")) or "(sin nombre)",
        "tipo_label": etiqueta_tipo(h),
        "motivo_exclusion": limpiar_texto(h.get("motivo_exclusion")) or "Sin datos suficientes este mes.",
        "ultima_posicion": ultima,
    }


def limpiar_config(config):
    vista = dict(config)
    for llave in ("nombre_sitio", "nombre_corto", "descripcion", "editor", "contacto", "editor_url", "url_publica"):
        if isinstance(vista.get(llave), str):
            vista[llave] = limpiar_texto(vista[llave])
    return vista


# ---------------------------------------------------------------------------
# Contexto completo para la plantilla.
# ---------------------------------------------------------------------------

def construir_contexto(config, ranking, historial):
    hospitales_raw = ranking.get("hospitales") or []
    raw_en_ranking = [h for h in hospitales_raw if h.get("en_ranking")]
    raw_fuera = [h for h in hospitales_raw if not h.get("en_ranking")]

    raw_en_ranking = sorted(
        raw_en_ranking,
        key=lambda h: (h.get("posicion") is None, h.get("posicion") if isinstance(h.get("posicion"), (int, float)) else 0),
    )

    repetidos = {}
    for h in raw_en_ranking:
        n = limpiar_texto(h.get("nombre_google")) or "(sin nombre)"
        repetidos[n] = repetidos.get(n, 0) + 1
    hospitales = [preparar_hospital(h, historial, repetidos) for h in raw_en_ranking]
    fuera = [preparar_hospital_fuera(h, historial) for h in raw_fuera]

    podio = hospitales[:3]
    provincias = sorted({h["provincia"] for h in hospitales if h["provincia"] and h["provincia"] != "N/D"})

    subidas = sorted(
        (h for h in hospitales if h["cambio"]["tipo"] == "subio"),
        key=lambda h: h["cambio"]["valor"], reverse=True,
    )[:3]
    bajadas = sorted(
        (h for h in hospitales if h["cambio"]["tipo"] == "bajo"),
        key=lambda h: h["cambio"]["valor"], reverse=True,
    )[:3]
    if "hay_edicion_anterior" in ranking:
        primera_edicion = not ranking.get("hay_edicion_anterior")
    else:
        primera_edicion = not any(h.get("posicion_anterior") is not None for h in raw_en_ranking)

    parametros = ranking.get("parametros") or {}
    pesos = parametros.get("pesos") or config.get("pesos") or {}
    minimo_resenas = parametros.get("minimo_resenas")
    if minimo_resenas is None:
        minimo_resenas = config.get("minimo_resenas_para_ranking")
    meta = {
        "m_fmt": fmt_num(parametros.get("m"), 0),
        "C_fmt": fmt_num(parametros.get("C"), 2),
        "peso_calificacion": redondear_pct(pesos.get("calificacion_ajustada")),
        "peso_volumen": redondear_pct(pesos.get("volumen")),
        "minimo_resenas_fmt": fmt_num(minimo_resenas, 0),
    }

    universo = ranking.get("universo") or {}

    url_base = (config.get("url_publica") or "").rstrip("/")
    base_datos = (config.get("url_datos_base") or "").rstrip("/")
    csv_url = f"{base_datos}/data/latest.csv" if base_datos else "data/latest.csv"
    json_url = f"{base_datos}/data/latest.json" if base_datos else "data/latest.json"
    historial_url = f"{base_datos}/data/historial.json" if base_datos else "data/historial.json"
    csv_url_absoluto = f"{url_base}/{csv_url}" if url_base else csv_url

    jsonld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": limpiar_texto(config.get("nombre_sitio")),
        "description": limpiar_texto(config.get("descripcion")),
        "dateModified": ranking.get("generado"),
        "url": config.get("url_publica"),
        "distribution": {
            "@type": "DataDownload",
            "encodingFormat": "text/csv",
            "contentUrl": csv_url_absoluto,
        },
    }

    return {
        "config": limpiar_config(config),
        "periodo": ranking.get("periodo"),
        "etiqueta_periodo": limpiar_texto(ranking.get("etiqueta_periodo")),
        "fuente": limpiar_texto(ranking.get("fuente")),
        "capturado_fmt": fmt_fecha_larga(ranking.get("capturado")),
        "generado_fmt": fmt_fecha_larga(ranking.get("generado")),
        "generado_iso": ranking.get("generado"),
        "proxima_fmt": fmt_fecha_larga(ranking.get("proxima_actualizacion")),
        "universo": universo,
        "hospitales": hospitales,
        "fuera": fuera,
        "podio": podio,
        "provincias": provincias,
        "subidas": subidas,
        "bajadas": bajadas,
        "primera_edicion": primera_edicion,
        "meta": meta,
        "csv_url": csv_url,
        "json_url": json_url,
        "historial_url": historial_url,
        "ruta_fuentes": config.get("ruta_fuentes") or "fonts/",
        "logo_blanco": config.get("logo_blanco") or "img/flow-logo-white.png",
        "url_actualizacion": config.get("url_actualizacion") or "",
        "periodo": ranking.get("periodo"),
        "jsonld": jsonld,
        "tiene_historial": bool(historial),
    }


# ---------------------------------------------------------------------------
# Escritura de docs/data/*
# ---------------------------------------------------------------------------

def escribir_csv(ruta: Path, hospitales_raw):
    filas = sorted(
        hospitales_raw,
        key=lambda h: (h.get("posicion") is None, h.get("posicion") if isinstance(h.get("posicion"), (int, float)) else 0),
    )
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=CSV_COLUMNAS, extrasaction="ignore")
        escritor.writeheader()
        for h in filas:
            fila = {col: ("" if h.get(col) is None else h.get(col)) for col in CSV_COLUMNAS}
            escritor.writerow(fila)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def encontrar_ranking_mas_reciente(directorio: Path) -> Path:
    patron = re.compile(r"^\d{4}-\d{2}\.json$")
    candidatos = sorted(p for p in directorio.glob("*.json") if patron.match(p.name))
    if not candidatos:
        sys.exit(
            f"No encontré ningún archivo AAAA-MM.json en {directorio} "
            "(fixture.json no cuenta como edición real). Use --ranking para indicar uno."
        )
    return candidatos[-1]


def cargar_json(ruta: Path):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Genera docs/ (sitio estático) del Ranking de Reputación Hospitalaria de Costa Rica."
    )
    p.add_argument(
        "--ranking", type=Path, default=None,
        help="Ruta al JSON de ranking del mes. Por defecto: el data/ranking/AAAA-MM.json más reciente (ignora fixture.json).",
    )
    p.add_argument(
        "--historial", type=Path, default=RAIZ / "data" / "historial.json",
        help="Ruta al historial. Por defecto data/historial.json; si no existe, el sitio se genera sin historial.",
    )
    p.add_argument("--config", type=Path, default=RAIZ / "config.json", help="Ruta a config.json.")
    p.add_argument("--out", type=Path, default=RAIZ / "docs", help="Carpeta de salida (por defecto docs).")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if not args.config.exists():
        sys.exit(f"No existe config.json en: {args.config}")
    config = cargar_json(args.config)

    ranking_path = args.ranking or encontrar_ranking_mas_reciente(RAIZ / "data" / "ranking")
    if not ranking_path.exists():
        sys.exit(f"No existe el archivo de ranking: {ranking_path}")
    ranking = cargar_json(ranking_path)

    historial = None
    if args.historial and Path(args.historial).exists():
        historial = cargar_json(args.historial)
    else:
        print(f"Aviso: sin historial ({args.historial}). El sitio se genera sin series de tendencia.", file=sys.stderr)

    out_dir = Path(args.out)
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    contexto = construir_contexto(config, ranking, historial)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["fmt_num"] = fmt_num
    plantilla = env.get_template("index.html.j2")
    html = plantilla.render(**contexto)
    (out_dir / "index.html").write_text(html, encoding="utf-8")

    escribir_csv(data_dir / "latest.csv", ranking.get("hospitales") or [])
    (data_dir / "latest.json").write_text(json.dumps(ranking, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / "historial.json").write_text(json.dumps(historial or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Listo: {out_dir / 'index.html'} ({len(contexto['hospitales'])} hospitales en el ranking, {len(contexto['fuera'])} fuera).")


if __name__ == "__main__":
    main()
