# Revisión de código y producto: ranking de reputación hospitalaria CR

Fecha de la revisión: 21 de setiembre de 2026. Commit revisado: 9a047f4 ("Alcance publicado: solo hospitales privados; nombres repetidos distinguidos por cantón"), árbol de trabajo limpio al momento de revisar.

## Resumen

Veredicto: listo con correcciones. El cálculo del índice, los deltas mes a mes, los hospitales nuevos, los que fallan y los que quedan fuera del censo se comportan bien: lo comprobé ejecutando `score.py` y `build_site.py` en una copia aislada del repositorio, incluida una simulación completa de una segunda edición (octubre). Antes de la corrida real de octubre conviene resolver dos cosas con severidad alta: seis hospitales del censo (cuatro de ellos privados y activos en el ranking publicado) no tienen `cid` ni `maps_url` fijos y dependen de una búsqueda por nombre en Google cada mes, y el mensaje "primera edición" se dispara mal en cualquier mes futuro donde, por coincidencia, ningún hospital cambie de puesto. El resto de los hallazgos son mejoras de robustez y de producto (buscador que no ignora tildes, contraste de un gris, sparkline con huecos cuando un hospital falla un mes, documentación desalineada con el alcance privados solamente) que no bloquean la publicación. No encontré guion largo, barra vertical, fuga de la llave de Firecrawl en el repositorio ni problemas con el CSV o el JSON-LD generados.

### Verificado sin hallazgos

- Aritmética del índice (promedio bayesiano, volumen logarítmico, desempate) reproducida a mano y por script: idéntica a la publicada.
- Llave de Firecrawl: nunca se imprime en `fc.py`, el workflow la inyecta solo en el paso de captura vía secreto de GitHub (que se redacta en los logs), y `publicar.sh` la sube sin hacer eco. Los `.log` quedan fuera de git por `.gitignore` y los `.txt`/`.json` trackeados en `data/raw/` no contienen ninguna cadena relacionada con Firecrawl, Bearer o API key.
- Límite de ritmo de Firecrawl: `fc.py` reparte máximo 10 solicitudes por minuto entre todos los hilos (con margen bajo el límite real del plan) y reintenta con espera creciente ante HTTP 429.
- Concurrencia del workflow: `concurrency` con `cancel-in-progress: false` encola corridas superpuestas en vez de cruzarlas; una segunda corrida del mismo mes no duplica commits porque `capturar` reutiliza lo ya guardado y el paso de publicación aborta si no hay cambios en el árbol.
- `docs/data/latest.csv` abre limpio con `csv.DictReader` y trae las columnas prometidas en `build_site.py`; el JSON-LD embebido parsea correctamente como `Dataset` de schema.org; las metaetiquetas Open Graph y el título están presentes.
- Cero apariciones de guion largo o barra vertical en `docs/index.html`, `docs/data/latest.json`, `docs/data/latest.csv`, `docs/data/historial.json`, el snapshot y el censo.
- No hay `id` ni `cid` duplicados dentro de `data/hospitales.json`.

## Tabla de hallazgos

<table>
<tr><th>Severidad</th><th>Archivo y línea</th><th>Qué está mal</th><th>Cómo reproducirlo</th><th>Corrección propuesta</th></tr>

<tr>
<td>Alta</td>
<td><code>data/hospitales.json</code> (6 registros; sin línea única útil)</td>
<td>Seis hospitales del censo no tienen <code>cid</code> ni <code>maps_url</code>: <code>hospital-manuel-mora-valverde</code>, <code>hospital-los-chiles</code> (públicos, hoy fuera de alcance) y <code>hospital-metropolitano-quepos</code>, <code>hospital-metropolitano-lincoln-plaza-moravia</code>, <code>hospital-clinica-santa-rita-san-jose</code>, <code>hospital-cristiano-jerusalen-guadalupe</code> (privados, sí entran al ranking publicado). Para ellos, <code>capturar_uno()</code> en <code>pipeline/gmaps.py</code> no visita una ficha fija sino que busca por nombre en Google Maps cada mes (rama <code>ficha_por_nombre</code>) y toma el <code>cid</code> que ese resultado traiga ese día. Esto contradice el propio contrato de <code>data/ESQUEMA.md</code>, que describe <code>cid</code> como "la llave para cruzar meses". Si algún mes la búsqueda por nombre devuelve un perfil distinto (otro local parecido, empate en el orden de resultados, Google reindexando el perfil), el hospital pierde su historial sin ningún aviso: <code>score.py</code> lo trataría como hospital nuevo y el <code>cid</code> anterior queda huérfano en <code>data/historial.json</code> para siempre.</td>
<td><code>python3 -c "import json; c=json.load(open('data/hospitales.json')); print([h['id'] for h in c if not h.get('cid')])"</code> devuelve los 6 identificadores. Confirmé además que en el snapshot de setiembre esos 6 sí traen un <code>cid</code> derivado en el momento de la captura, con URLs de Maps con formato de búsqueda en vivo (<code>/place/.../@lat,lng,17z</code>), distinto del formato de permalink guardado (<code>!1s0x...</code>) que sí tienen los otros 49 hospitales.</td>
<td>Buscar una vez la ficha de cada uno de los 6 en Google Maps y completar <code>maps_url</code> y <code>cid</code> a mano en <code>data/hospitales.json</code>, igual que está hecho para el resto del censo. Así <code>capturar_uno()</code> deja de depender de la búsqueda por nombre para ellos.</td>
</tr>

<tr>
<td>Alta</td>
<td><code>pipeline/build_site.py</code>, línea 329</td>
<td><code>primera_edicion = not subidas and not bajadas</code> infiere que es la primera edición del ranking a partir de que nadie subió ni bajó de puesto, en vez de a partir de si existe una edición anterior real. En cualquier mes futuro (segundo, tercero o el que sea) donde, por casualidad, ningún hospital cambie de posición, el sitio va a mostrar por error el mensaje "Esta es la primera edición del ranking. Los cambios de posición van a aparecer a partir de la siguiente actualización.", aunque haya meses de historia real detrás.</td>
<td>Lo reproduje de forma aislada llamando directamente a <code>construir_contexto()</code> con un ranking sintético de 2 hospitales que sí tienen <code>posicion_anterior</code> fijado (1 y 2) pero <code>delta_posicion = 0</code> en ambos: <code>subidas</code> y <code>bajadas</code> salen vacías y <code>primera_edicion</code> da <code>True</code>, a pesar de que ambos hospitales traen historial previo.</td>
<td>Calcular la bandera a partir de si existe un ranking anterior, no de listas de cambios vacías: por ejemplo, que <code>score.py</code> escriba explícitamente en el JSON si encontró <code>ranking_anterior</code> (ya lo sabe, línea 131), y que <code>build_site.py</code> use ese campo, o en su defecto que revise si algún hospital trae <code>posicion_anterior is not None</code>.</td>
</tr>

<tr>
<td>Media</td>
<td><code>pipeline/build_site.py</code>, líneas 173 a 199 (<code>construir_sparkline</code>)</td>
<td>El sparkline de tendencia espacia los puntos según <code>len(serie)</code> (cantidad de meses con dato para ese hospital), no según su posición real en el calendario. Si un hospital falla un mes (error o queda fuera del alcance) y vuelve más adelante, el hueco desaparece visualmente: el gráfico une los meses como si fueran consecutivos.</td>
<td>En la simulación de octubre, "Hospital Clínica Alpha" pasó a estado de error. Su registro en <code>data/historial.json</code> quedó con un único punto (setiembre); si vuelve a tener datos en noviembre, la serie tendrá sep y nov pero el sparkline los va a dibujar pegados, como si octubre no hubiera existido.</td>
<td>Calcular la posición horizontal de cada punto a partir del periodo real (usar la lista global <code>historial.periodos</code> para ubicar cada punto en su lugar del calendario) en vez de usar el índice dentro de la propia serie del hospital, o al menos marcar visualmente el hueco.</td>
</tr>

<tr>
<td>Media</td>
<td><code>pipeline/templates/index.html.j2</code>, líneas 299, 480 y 524</td>
<td>El buscador de texto del sitio compara <code>data-nombre</code> (el nombre en minúsculas, pero con tildes) contra lo que la persona escribe, sin normalizar acentos. Buscar "biblica" o "mexico" sin tilde (algo muy común al escribir desde el celular) no encuentra "Hospital Clínica Bíblica" ni "Hospital México", aunque ambos existen en el ranking. El propio pipeline ya tiene una función que quita tildes para comparar nombres (<code>normalizar()</code> en <code>pipeline/gmaps.py</code>), pero el sitio no la usa en el buscador.</td>
<td>En el sitio publicado, escribir <code>biblica</code> o <code>mexico</code> en el campo "Buscar hospital" y ver que no aparece ningún resultado pese a que esos hospitales están en la tabla.</td>
<td>Normalizar (quitar diacríticos) tanto <code>data-nombre</code> como el texto que escribe la persona antes de comparar, con la misma lógica que ya existe en <code>normalizar()</code> del lado Python, portada a JavaScript.</td>
</tr>

<tr>
<td>Media</td>
<td><code>pipeline/templates/index.html.j2</code>, línea 46 (variable) y usos en líneas 124, 135 y 197</td>
<td>El gris <code>--color-muted-claro: #8a8a8a</code> sobre fondo blanco da un contraste aproximado de 3.45 a 1, por debajo del mínimo de accesibilidad (4.5 a 1) para texto de tamaño normal. Se usa en la ubicación de cada hospital (provincia y cantón bajo el nombre), en la etiqueta "igual" de la columna Cambio, y en las etiquetas de columna que aparecen en la vista móvil.</td>
<td>Cálculo de contraste con la fórmula estándar de luminancia relativa de WCAG sobre <code>#8a8a8a</code> contra <code>#ffffff</code>: da 3.45 a 1. Cualquier verificador de contraste (por ejemplo el de WebAIM) lo confirma.</td>
<td>Oscurecer ese gris a uno que dé al menos 4.5 a 1 sobre blanco (un valor de referencia habitual es <code>#767676</code>, que da justo 4.5 a 1).</td>
</tr>

<tr>
<td>Media</td>
<td><code>README.md</code> líneas 3 y 4, <code>data/ESQUEMA.md</code> línea 65</td>
<td>La documentación describe un ranking de "todos los hospitales de Costa Rica (públicos y privados)" y el ejemplo de <code>data/ESQUEMA.md</code> muestra <code>"universo": {"publicos": 30, "privados": 32, ...}</code>. Pero <code>config.json</code> fija <code>tipos_incluidos: ["privado"]</code>, así que en la práctica <code>universo.publicos</code> siempre da 0. Quien llegue al repositorio sin contexto (o retome el proyecto en unos meses) puede pensar que el alcance sigue siendo ambos tipos.</td>
<td>Leer README.md y ESQUEMA.md junto a config.json: el primero no menciona el alcance privados solamente, el segundo tiene un ejemplo con números públicos que ya no ocurren.</td>
<td>Actualizar ambos documentos para reflejar el alcance actual (el propio sitio generado sí lo explica bien, en la sección de Metodología, así que puede tomarse ese texto como referencia).</td>
</tr>

<tr>
<td>Media</td>
<td><code>pipeline/build_site.py</code>, líneas 281 a 286 (<code>preparar_hospital_fuera</code>)</td>
<td>Un hospital que pasa de estar en el ranking a quedar sin datos (por ejemplo, error de lectura ese mes) pierde toda referencia a su historia: la sección "Fuera del ranking" solo muestra nombre y motivo, sin decir en qué puesto estaba el mes anterior.</td>
<td>En la simulación de octubre, "Hospital Clínica Alpha" (puesto 9 en setiembre) pasa a "Fuera del ranking" mostrando únicamente "Sin datos este mes: Google no mostró calificación o total de reseñas", sin mencionar su puesto anterior.</td>
<td>Cuando el hospital tenía <code>cid</code> y estaba rankeado el mes anterior, agregar algo como "última posición conocida: puesto 9 en setiembre 2026", usando el historial.</td>
</tr>

<tr>
<td>Media</td>
<td><code>pipeline/actualizar.py</code> línea 41; <code>pipeline/gmaps.py</code> <code>parsear_lista</code> y <code>parsear_ficha</code></td>
<td>La única red de seguridad ante un cambio de Google es el umbral del 80% de fichas leídas (<code>ok/total &lt; args.umbral</code>). Ese umbral detecta bien una rotura masiva (por ejemplo, si Google cambia una clase y ya nada se lee), porque ahí <code>calificacion</code> y <code>resenas</code> quedan en <code>None</code> y el hospital sale marcado con error. Pero no detecta el caso más peligroso: que un cambio de markup haga que el selector encuentre un elemento equivocado y devuelva un número que parece válido pero no lo es (una calificación o un total de reseñas incorrectos, sin que <code>error</code> se active). Ese caso pasa completamente silencioso, tanto para la persona que revisa como para el 80%.</td>
<td>No ocurrió en los datos actuales: es un análisis de código (no hay ningún control de rango ni de variación mes a mes sobre <code>calificacion</code> o <code>resenas</code> en <code>score.py</code> ni en <code>actualizar.py</code>).</td>
<td>Agregar una verificación de plausibilidad además del umbral de completitud: por ejemplo, avisar (sin necesariamente bloquear la publicación) si <code>calificacion</code> sale fuera de 1 a 5, o si <code>resenas</code> cambia más de cierto porcentaje respecto al mes anterior para el mismo <code>cid</code>. El umbral del 80% por sí solo no es suficiente para este segundo caso.</td>
</tr>

<tr>
<td>Baja</td>
<td><code>pipeline/score.py</code>, línea 73</td>
<td>Los hospitales cuyo <code>tipo</code> no está en <code>tipos_incluidos</code> (hoy, los públicos que todavía aparecen en el snapshot de setiembre) se descartan antes de construir <code>filas</code>, así que no quedan ni en la tabla principal ni en "Fuera del ranking": desaparecen sin dejar ningún rastro ni conteo. Hoy no es un problema real porque la Metodología del sitio explica el alcance privados solamente, pero si algún mes <code>capturar</code> corre con <code>--todos</code> o el snapshot vuelve a traer públicos, no queda ningún número de cuántos se excluyeron por tipo.</td>
<td>Lo confirmé agregando a la simulación de octubre un hospital inventado sin registro en el censo (<code>hospital-fantasma-inventado</code>): no aparece ni en <code>hospitales</code> ni en <code>fuera</code> del <code>data/ranking/2026-10.json</code> resultante, ni genera ningún error.</td>
<td>Opcional: sumar un contador de "excluidos por tipo" al bloque <code>universo</code> o al log de <code>score.py</code>, sin necesidad de mostrarlo en el sitio.</td>
</tr>

<tr>
<td>Baja</td>
<td><code>pipeline/templates/index.html.j2</code>, líneas 256 a 262</td>
<td>Cuando <code>tipos_incluidos = ["privado"]</code>, los tres botones de pestaña (Todos, Privados, Públicos) se ocultan correctamente, pero el <code>div</code> que los envuelve (<code>role="group" aria-label="Filtrar por tipo de hospital"</code>) se sigue renderizando vacío. Un lector de pantalla anuncia un grupo sin ningún control adentro.</td>
<td>Inspeccionar <code>docs/index.html</code> generado: el <code>div.tabs</code> existe sin ningún <code>button</code> dentro cuando el ranking es privados solamente.</td>
<td>Envolver también ese <code>div</code> en la condición <code>{% if not solo_privados %}</code>.</td>
</tr>

<tr>
<td>Baja</td>
<td><code>pipeline/build_site.py</code>, líneas 122 a 128 (<code>etiqueta_tipo</code>) y campos <code>telefono</code>, <code>config.contacto</code>, <code>config.editor_url</code></td>
<td><code>limpiar_texto()</code> (que quita guion largo y barra vertical) se aplica a nombre, provincia, cantón, dirección y a los textos de <code>config.json</code> usados en cabecera y pie, pero no a <code>red</code>/<code>clasificacion</code> (usados dentro de <code>etiqueta_tipo</code>), ni a <code>telefono</code>, ni a <code>config.contacto</code> o <code>config.editor_url</code>. Hoy el riesgo real es bajo porque son valores de vocabulario controlado o escritos a mano, pero la protección queda dispareja.</td>
<td>Lectura de código: comparar qué campos pasan por <code>limpiar_texto()</code> en <code>preparar_hospital()</code> y <code>limpiar_config()</code> contra los que no.</td>
<td>Pasar esos campos también por <code>limpiar_texto()</code>, por consistencia, aunque hoy no esté causando ningún problema visible.</td>
</tr>

<tr>
<td>Baja</td>
<td><code>pipeline/build_site.py</code>, líneas 438, 441 a 442 y 453</td>
<td>A diferencia de <code>score.py</code> y <code>gmaps.py</code> (que resuelven rutas con <code>RAIZ</code>, basado en la ubicación del propio archivo), <code>build_site.py</code> resuelve sus rutas por defecto (<code>data/ranking</code>, <code>data/historial.json</code>, <code>config.json</code>) relativas al directorio de trabajo desde el que se invoca. Hoy no falla porque <code>actualizar.py</code> siempre lo llama con <code>cwd=RAIZ</code> (la raíz del repositorio) y porque el README lo documenta corriéndose desde ahí, pero rompe el patrón del resto del pipeline: si alguien lo corre a mano desde otra carpeta, corta con un <code>sys.exit</code> claro en vez de generar el sitio.</td>
<td>Correr <code>python3 pipeline/build_site.py</code> parado dentro de <code>pipeline/</code> en vez de en la raíz del repositorio: termina con "No existe config.json en: config.json".</td>
<td>Usar el mismo patrón de <code>RAIZ</code> basado en <code>__file__</code> que <code>score.py</code>, o documentar explícitamente que debe correrse desde la raíz.</td>
</tr>

<tr>
<td>Baja</td>
<td><code>pipeline/requirements.txt</code></td>
<td>No fija el paquete <code>tzdata</code>. <code>zoneinfo.ZoneInfo("America/Costa_Rica")</code> (usado en <code>gmaps.py</code> y <code>score.py</code>) depende de que la base de datos IANA esté instalada en el sistema operativo. El runner <code>ubuntu-latest</code> de GitHub Actions normalmente la trae instalada de fábrica, así que hoy no debería fallar, pero es una dependencia implícita, no declarada.</td>
<td>Revisar <code>pipeline/requirements.txt</code>: solo lista <code>requests</code>, <code>jinja2</code>, <code>beautifulsoup4</code> y <code>lxml</code>.</td>
<td>Agregar <code>tzdata</code> como red de seguridad barata (no tiene costo si el sistema operativo ya la trae).</td>
</tr>

</table>

## Resultado de la simulación del segundo mes

Para no tocar el repositorio real, armé una copia aislada del pipeline y los datos en un directorio de trabajo temporal (no en `/tmp` del sistema ni dentro del repositorio) y ejecuté ahí todas las pruebas. Esto cumple el mismo objetivo que copiar a `/tmp/sim/` y luego restaurar `data/historial.json`, pero sin ningún riesgo de dejar algo a medio restaurar en el repositorio real: nunca escribí en `data/ranking/2026-10.json` ni en `data/historial.json` del repositorio, porque todo corrió sobre la copia.

Primero confirmé determinismo: corrí `score.py --periodo 2026-09` y `build_site.py` sobre la copia, con los mismos `data/hospitales.json`, `config.json` y `data/snapshots/2026-09.json` reales, y el resultado fue idéntico al `data/ranking/2026-09.json` ya publicado (mismo orden, mismos índices, mismos 24 en el ranking y 1 fuera), salvo el campo `generado`, que siempre lleva la hora de la corrida.

Después armé un snapshot de octubre a partir del de setiembre, con cambios deliberados sobre hospitales reales del censo:

- Dos hospitales suben (Hospital CIMA: pasó del puesto 16 al 7; Hospital Universal: del 8 al 6), con calificación y reseñas al alza.
- Dos hospitales bajan como consecuencia (Hospital Metropolitano, sede Moravia: del 13 al 22, con caída directa de calificación; y otros dos que cedieron lugar por el ascenso de los anteriores).
- Un hospital nuevo en el ranking: Clínica Santa Rita, que en setiembre tenía 8 reseñas (debajo del mínimo de 10) y en la simulación sube a 16, entra al ranking en el puesto 17 con `posicion_anterior` en null y la insignia "nuevo".
- Un hospital con error de captura: Hospital Clínica Alpha (puesto 9 en setiembre) queda sin calificación ni reseñas este mes; pasa a "Fuera del ranking" con el motivo correcto, sin ninguna excepción ni corte del script.
- Un hospital inventado sin registro en el censo (`hospital-fantasma-inventado`), para confirmar qué pasa con un identificador desconocido: desaparece sin dejar rastro en ninguna parte del `data/ranking/2026-10.json` resultante (hallazgo de severidad baja ya anotado en la tabla).

Con `score.py --periodo 2026-10 --snapshot <copia modificada>` el cálculo corrió sin errores: 24 hospitales en el ranking, 1 fuera, `data/historial.json` de la copia quedó con los periodos `2026-09` y `2026-10`. Los deltas de posición, calificación y reseñas salieron correctos para los que subieron, bajaron, entraron y salieron. `build_site.py` regeneró el sitio de la copia sin errores: la sección "Qué cambió este mes" mostró bien "Hospital CIMA: sube 9 puestos" y "Hospital Metropolitano (Moravia): baja 9 puestos", con el plural correcto; la insignia "nuevo" apareció junto a Clínica Santa Rita; "Fuera del ranking" mostró a Hospital Clínica Alpha con su motivo; cero apariciones de guion largo o barra vertical en el HTML generado.

Esta misma simulación fue la que dejó evidencia directa de dos hallazgos de la tabla: el hueco en el sparkline de Alpha (su serie en el historial quedó con un solo punto, el de setiembre, listo para "pegarse" mal si vuelve en un mes futuro) y la pérdida de contexto en "Fuera del ranking" (Alpha no menciona que estaba en el puesto 9). El hallazgo de "primera edición" lo probé aparte, con un ranking sintético mínimo, porque la simulación de octubre sí tuvo subidas y bajadas reales y por lo tanto no disparaba ese caso.

## Confirmación de modo solo lectura

No modifiqué ningún archivo del repositorio real. Todas las corridas de `score.py` y `build_site.py` se hicieron sobre una copia en un directorio de trabajo temporal fuera del repositorio; los archivos `data/ranking/2026-10.json` y `data/historial.json` que esas corridas escriben quedaron únicamente en esa copia, nunca en `/Users/robertoecheverria/ranking-reputacion-hospitales-cr`. El único archivo que agrego al repositorio es este mismo reporte, `data/raw/revision_codigo.md`. `git status --short` antes de escribirlo mostraba el árbol limpio en `data/` y `docs/` (el commit `9a047f4` y un archivo `data/raw/revision_datos.md` aparecieron durante la revisión por actividad ajena a esta sesión, no por algo que yo haya ejecutado).
