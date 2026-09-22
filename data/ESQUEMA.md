# Contrato de datos

Todos los scripts y la plantilla del sitio leen y escriben exclusivamente estos archivos.

## `data/hospitales.json` (censo curado, lo edita una persona)
Lista de hospitales que ENTRAN al ranking. Es la lista blanca: el scraper solo rankea lo que está aquí.
```json
[
  {
    "id": "hospital-clinica-biblica-san-jose",
    "nombre_google": "Hospital Clínica Bíblica",
    "alias": ["Clínica Bíblica", "Hospital Clínica Bíblica San José"],
    "tipo": "privado",
    "red": "Privado",
    "clasificacion": "privado",
    "provincia": "San José",
    "canton": "San José",
    "sitio_web": "https://www.clinicabiblica.com/",
    "maps_url": "https://www.google.com/maps/place/Hospital+Cl%C3%ADnica+B%C3%ADblica/data=!4m7!3m6!1s0x8fa0e368060ebcc1:0xf9defc9ecd48e56e...",
    "cid": "0x8fa0e368060ebcc1:0xf9defc9ecd48e56e",
    "fuentes": ["https://ach.sa.cr/directorio/..."],
    "notas": ""
  }
]
```
- `tipo`: `publico` o `privado`.
- `red`: `CCSS`, `INS`, `Privado`, `Universitario`, `Otro`.
- `clasificacion` (solo públicos CCSS): `nacional`, `especializado`, `regional`, `periferico`; privados: `privado`.
- `cid`: identificador del perfil de Google que aparece en la URL de Maps (`!1s0x...:0x...`). Es la llave para cruzar meses.

## `data/snapshots/AAAA-MM.json` (lo escribe el scraper, un archivo por mes)
```json
{
  "periodo": "2026-09",
  "capturado": "2026-09-21T22:40:00-06:00",
  "fuente": "Google Business Profile (Google Maps) vía Firecrawl",
  "hospitales": [
    {
      "id": "hospital-clinica-biblica-san-jose",
      "cid": "0x8fa0e368060ebcc1:0xf9defc9ecd48e56e",
      "nombre_google": "Hospital Clínica Bíblica",
      "categoria_google": "Hospital",
      "calificacion": 4.6,
      "resenas": 2001,
      "distribucion": {"5": 1500, "4": 200, "3": 80, "2": 60, "1": 161},
      "direccion": "...", "telefono": "+506 2522 1000", "sitio_web": "https://www.clinicabiblica.com/",
      "maps_url": "https://www.google.com/maps/place/...",
      "muestra_resenas": {"visibles": 8, "con_respuesta": 3},
      "estado": "abierto",
      "error": null
    }
  ]
}
```
`distribucion` y `muestra_resenas` pueden venir `null` si Google no los mostró ese mes. `error` trae texto si el perfil no se pudo leer. `estado` es `abierto`, `cerrado_temporalmente` o `cerrado_permanentemente` (los cerrados quedan fuera del ranking). Solo se rankean los `tipo` incluidos en `config.json` (`tipos_incluidos`); el resto cuenta en `universo.fuera_de_alcance`.

## `data/ranking/AAAA-MM.json` (lo escribe `score.py`; es lo que consume el sitio)
```json
{
  "periodo": "2026-09",
  "etiqueta_periodo": "Edición de septiembre de 2026",
  "generado": "2026-09-21T22:45:00-06:00",
  "capturado": "2026-09-21T22:40:00-06:00",
  "proxima_actualizacion": "2026-10-01",
  "fuente": "Google Business Profile (Google Maps) vía Firecrawl",
  "hay_edicion_anterior": false,
  "periodo_anterior": null,
  "universo": {"total": 24, "publicos": 0, "privados": 24, "sin_datos": 1, "fuera_de_alcance": 30},
  "parametros": {"m": 141, "C": 4.01, "pesos": {"calificacion_ajustada": 0.75, "volumen": 0.25}, "minimo_resenas": 25, "tipos_incluidos": ["privado"]},
  "hospitales": [
    {
      "id": "hospital-clinica-biblica-san-jose",
      "cid": "0x8fa0e368060ebcc1:0xf9defc9ecd48e56e",
      "nombre_google": "Hospital Clínica Bíblica",
      "tipo": "privado", "red": "Privado", "clasificacion": "privado",
      "categoria_google": "Hospital",
      "provincia": "San José", "canton": "San José",
      "direccion": "...", "sitio_web": "https://...", "telefono": "...",
      "maps_url": "https://www.google.com/maps/place/...",
      "calificacion": 4.6, "resenas": 2001,
      "distribucion": {"5": 1500, "4": 200, "3": 80, "2": 60, "1": 161},
      "pct_5": 75.0, "pct_1": 8.0,
      "calificacion_ajustada": 4.52,
      "puntaje_calificacion": 88.0, "puntaje_volumen": 100.0,
      "indice": 91.0,
      "posicion": 1, "posicion_tipo": 1,
      "posicion_anterior": null, "delta_posicion": null,
      "calificacion_anterior": null, "delta_calificacion": null,
      "resenas_anterior": null, "delta_resenas": null,
      "muestra_resenas": {"visibles": 8, "con_respuesta": 3, "pct_respuesta": 37.5},
      "en_ranking": true, "motivo_exclusion": null
    }
  ]
}
```
- `posicion` es el puesto en el ranking general; `posicion_tipo` es el puesto dentro de su tipo (público o privado).
- Los campos `*_anterior` y `delta_*` comparan contra el ranking del mes anterior por `cid`; van `null` el primer mes o si el hospital es nuevo.
- `en_ranking: false` cuando no alcanza el mínimo de reseñas o no hubo datos; esos hospitales se listan aparte, sin posición.

## `data/historial.json` (lo mantiene `score.py`)
```json
{"periodos": ["2026-09", "2026-10"], "hospitales": {"<cid>": {"nombre_google": "...", "serie": [{"periodo": "2026-09", "posicion": 1, "indice": 91.0, "calificacion": 4.6, "resenas": 2001}]}}}
```

## Salida del sitio (`docs/`)
- `docs/index.html` generado por `pipeline/build_site.py` desde la plantilla `pipeline/templates/index.html.j2`.
- `docs/data/latest.json` (copia del ranking del mes), `docs/data/latest.csv`, `docs/data/historial.json`.
