# Ranking de Reputación Hospitalaria de Costa Rica

Sitio estático que ordena los hospitales privados de Costa Rica según la reputación que muestran sus
perfiles públicos de Google (Google Business Profile). Se actualiza solo el día 1 de cada mes con GitHub
Actions y se publica en GitHub Pages desde la carpeta `docs/`.

Alcance: `config.json` fija `tipos_incluidos: ["privado"]`. El censo (`data/hospitales.json`) también trae los
30 hospitales públicos (CCSS e INS) por si algún día se amplía el alcance, pero no se capturan ni se rankean.

## Cómo funciona

```
data/hospitales.json  (censo curado)          config.json (pesos, textos)
        │                                            │
        ▼                                            ▼
pipeline/gmaps.py capturar  ──►  data/snapshots/AAAA-MM.json   (lo que dijo Google ese mes)
                                             │
                                             ▼
pipeline/score.py            ──►  data/ranking/AAAA-MM.json + data/historial.json
                                             │
                                             ▼
pipeline/build_site.py       ──►  docs/index.html + docs/data/latest.{json,csv} + docs/data/historial.json
```

`pipeline/actualizar.py` encadena los tres pasos y falla si se leyó menos del 80% de las fichas.

## Motor de datos

Firecrawl (`pipeline/fc.py`) renderiza Google Maps y el extractor (`pipeline/gmaps.py`) lee, por hospital:
nombre tal como lo muestra Google, calificación, total de reseñas, distribución por estrellas, categoría,
dirección, teléfono, sitio web y cuántas de las reseñas visibles tienen respuesta del hospital.
Costo aproximado: una lectura de Firecrawl por hospital al mes (menos de 200 créditos mensuales).

## Índice de reputación (0 a 100)

1. Calificación ajustada (promedio bayesiano): `(n/(n+m))·calificación + (m/(n+m))·C`, con `n` reseñas del
   hospital, `m` mediana de reseñas del universo y `C` promedio nacional ponderado. Un hospital con pocas
   reseñas se acerca al promedio nacional hasta que acumula evidencia.
2. Volumen de voz: `log10(n+1) / log10(n_max+1)`.
3. Índice = 75% calificación ajustada (llevada a 0 a 100) + 25% volumen. Pesos en `config.json`.
4. Mínimo 20 reseñas para entrar al ranking (`minimo_resenas_para_ranking` en `config.json`).
5. Un perfil que Google marca como cerrado (permanente o temporalmente) queda fuera ese mes.

El porcentaje de reseñas de 5 y de 1 estrella y la tasa de respuesta son señales complementarias; no entran al índice.

## Correr a mano

```bash
pip install -r pipeline/requirements.txt
export FIRECRAWL_API_KEY=...            # o dejarla en ~/.bash_profile
python3 pipeline/actualizar.py          # captura + índice + sitio del mes actual
python3 pipeline/actualizar.py --sin-captura   # solo recalcular y regenerar
python3 pipeline/gmaps.py ficha "https://www.google.com/maps/place/..."   # probar una ficha
```

## Mantener el censo

- `data/hospitales.json` es la lista blanca: solo lo que está ahí entra al ranking.
- Para redescubrir perfiles nuevos: `python3 pipeline/gmaps.py descubrir` y luego
  `python3 pipeline/cruzar_censo.py`, que deja en `data/raw/perfiles_no_censados.json` los perfiles de Google
  con categoría de hospital que no están en el censo, para revisión humana.
- Para agregar un hospital: añadir la entrada con `id`, `nombre_google`, `tipo`, `red`, `clasificacion`,
  `provincia`, `canton` y `maps_url` (la URL de la ficha en Google Maps). El `cid` se toma de la URL.

## Publicación

- GitHub Pages sirve `docs/` desde la rama `main`.
- El workflow `.github/workflows/actualizacion-mensual.yml` corre el día 1 a las 07:00 de Costa Rica y
  también a mano desde la pestaña Actions ("Run workflow"). Necesita el secreto `FIRECRAWL_API_KEY`.
- Si un mes la captura falla, el workflow queda en rojo y el sitio conserva la edición anterior.

## Contrato de datos

Ver `data/ESQUEMA.md`.
