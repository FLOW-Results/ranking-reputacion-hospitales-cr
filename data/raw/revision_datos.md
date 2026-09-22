# Revisión de datos: ranking de reputación de hospitales privados de Costa Rica (edición 2026-09)

Auditoría de solo lectura sobre `data/hospitales.json`, `data/censo_candidatos.json`, `data/snapshots/2026-09.json`, `data/ranking/2026-09.json`, `config.json` y `pipeline/score.py`. No se modificó ningún archivo del repositorio.

## Resumen

1. Veredicto: publicable con correcciones menores.
2. El índice se reprodujo de forma independiente, fuera de `pipeline/score.py`, sobre los 24 hospitales rankeados: el desvío máximo fue 0.0 y las 24 posiciones coinciden. La fórmula está bien implementada.
3. Las identidades de los 25 privados están limpias: ningún cid ni combinación nombre más dirección se repite, y los tres perfiles "Hospital Metropolitano" (San José, Moravia, Lindora) y los dos "Hospital Clínica Bíblica" (San José, Santa Ana) corresponden a lugares físicos distintos y bien confirmados.
4. Hay un problema real de clasificación: Hospital Metropolitano Quepos aparece categorizado por Google como "Clínica ambulatoria" (verificado dos veces en vivo), lo que contradice el propio criterio de inclusión del censo. Conviene resolverlo antes de publicar.
5. Los 8 perfiles releídos en vivo coincidieron en calificación en el 100% de los casos (7 de 8 también en reseñas). Quedan pendientes menores de completitud y una advertencia de sentido común sobre Hospital Metropolitano Escazú (23 reseñas) ubicado arriba de Hospital CIMA (377 reseñas) en el ranking.

## Tabla de hallazgos

<table>
<tr><th>Severidad</th><th>Hospital o archivo</th><th>Qué está mal</th><th>Evidencia</th><th>Acción recomendada</th></tr>

<tr>
<td>Alta</td>
<td>hospital-metropolitano-quepos<br>(Hospital Metropolitano • Quepos)</td>
<td>Google categoriza este perfil como "Clínica ambulatoria", no como hospital. El criterio propio del censo (en <code>censo_candidatos.json</code>) dice textualmente: "Quedan fuera clínicas sin hospitalización... centros de cirugía ambulatoria". Esta sede está en un local comercial (#206) de la Marina Pez Vela, con horario de lunes a viernes de 9:00 a 18:00 y sábado medio día, sin evidencia de camas ni urgencias 24 horas. Fuentes externas describen la red Hospital Metropolitano como dueña de solo dos "hospitales" propiamente (San José y Lindora, este último con 5 camas de hospitalización según La Nación) y el resto como sedes o locales de consulta.</td>
<td><code>categoria_google</code> del snapshot y de dos lecturas en vivo (21 set, minutos aparte): "Clínica ambulatoria". Búsqueda: horario y servicios de la sede Quepos (facebook.com/metropolitanocr, theebsla.com). Artículo "Hospital Metropolitano abre nueva sede en Lindora" (La Nación).</td>
<td>Confirmar directamente con Hospital Metropolitano si la sede Quepos hospitaliza. Si no, moverla a "dudosos" o excluirla del censo privado y recalcular (pasaría de 24 a 23 hospitales rankeados; hoy ocupa la posición 17).</td>
</tr>

<tr>
<td>Media</td>
<td>config.json / Hospital Metropolitano Escazú vs. Hospital CIMA</td>
<td>Con el mínimo actual de 10 reseñas, un hospital de muy pocas reseñas puede superar en el ranking a uno con cientos. Hospital Metropolitano Escazú (4.3 con 23 reseñas) queda en la posición 15, arriba de Hospital CIMA (3.4 con 377 reseñas) en la posición 16. El cálculo está bien hecho (ver reproducción del índice), pero el resultado es difícil de defender ante un director de hospital o un periodista.</td>
<td><code>data/ranking/2026-09.json</code>: Escazú índice 67.7 (calificación ajustada 4.055), CIMA índice 67.7 (calificación ajustada 3.567); desempata por calificación ajustada.</td>
<td>No aplicado, se deja a criterio editorial: subir el mínimo de reseñas para entrar al ranking (por ejemplo a 25 o 30), o publicar un aviso de "muestra pequeña" en los hospitales con reseñas muy por debajo de la mediana (hoy 141), o dar más peso al volumen.</td>
</tr>

<tr>
<td>Media</td>
<td>hospital-metropolitano-lincoln-plaza-moravia y hospital-metropolitano-escazu</td>
<td>El propio censo ya marca estas dos sedes como no confirmadas de forma independiente ("No se confirmó si esta sede hospitaliza"). La lectura en vivo de Google sí las categoriza como "Hospital" en ambos casos, lo cual es una señal a favor, pero no se halló una fuente externa (prensa o sitio propio) que confirme camas de internamiento, a diferencia de Lindora.</td>
<td><code>censo_candidatos.json</code>, notas de ambas entradas. Snapshot y lectura en vivo: categoria_google "Hospital" para las dos.</td>
<td>Pedir confirmación directa (llamada o correo a Hospital Metropolitano) antes de la próxima edición. Por ahora se pueden mantener en el censo, apoyados en la categoría de Google.</td>
</tr>

<tr>
<td>Media</td>
<td>Completitud, provincia de Limón</td>
<td>Ninguno de los 25 privados está en Limón. Clínica Atlántica (razón social Servicios Privados en Salud SERPRISA S.A.), en Guápiles, anuncia en su propio sitio "medicina general e internamiento", pero no se autodenomina hospital ni confirma quirófanos o urgencias 24 horas. No apareció en ninguna de las 49 búsquedas de descubrimiento ya guardadas en <code>data/raw/descubrimiento-2026-09.json</code> (que sí incluyó "hospital Guápiles Costa Rica" y encontró únicamente el hospital público CCSS de esa consulta).</td>
<td>clinicaatlanticacr.com ("servicio de medicina general e internamiento"). Búsqueda propia en <code>descubrimiento-2026-09.json</code>: sin coincidencias para "atlántica" ni "Guápiles" salvo el hospital público.</td>
<td>Agregar a "dudosos" con estas fuentes, igual que Santa Catalina o Santa Fe, y decidir si califica. No es urgente: la evidencia de hospitalización real es débil.</td>
</tr>

<tr>
<td>Baja</td>
<td>Completitud, "Hospital Metropolitano Tibás"</td>
<td>Aparece en el directorio de la Asociación Costarricense de Hospitales (la misma fuente que ya usa el censo) y en directorios locales antiguos (Waze, Infoguia, Moovit), con teléfono y dirección propios. Pero no aparece en ninguna de las 49 búsquedas de descubrimiento ya corridas (incluida "hospital Tibás Costa Rica", que sí corrió y encontró otros resultados), ni en la página oficial vigente de sedes (metropolitanocr.com/nuestras-sedes). Lo más probable es que haya cerrado o se haya fusionado con otra sede, y que el directorio ACH esté desactualizado (igual que ya lo está para "Hospital La California").</td>
<td>ach.sa.cr/directorio/categorias/privado (listado "Hospital Metropolitano - Tibás"). <code>data/raw/descubrimiento-2026-09.json</code>: sin coincidencias para "Tibás" entre los resultados de tipo hospital.</td>
<td>Confirmación rápida (buscar si tiene ficha propia y activa en Google Maps) antes de descartarlo del todo. Baja prioridad.</td>
</tr>

<tr>
<td>Baja</td>
<td>hospital-clinica-senora-de-los-angeles-cartago</td>
<td>Google categoriza este perfil como "Centro médico", no "Hospital" (confirmado en el snapshot y de nuevo en la lectura en vivo). El sitio propio, en cambio, confirma explícitamente "servicio de Hospitalización", quirófanos y urgencias 24/7. Es una etiqueta imprecisa de Google, no un error de identidad del censo.</td>
<td>hospitalclinicalosangeles.com: "El servicio de Hospitalización... brinda atención médica integral"; "Atención inmediata y continua las 24 horas". Snapshot y lectura en vivo: categoria_google "Centro médico".</td>
<td>Ninguna acción sobre el censo. Opcional: anotar la discrepancia de categoría para no sorprenderse si alguien la señala.</td>
</tr>

<tr>
<td>Baja</td>
<td>hospital-cristiano-jerusalen-guadalupe (Google: "Hospital Jerusalem")</td>
<td>Identidad confirmada: mismo teléfono (+506 2216 9191), misma dirección (Alto de Guadalupe, 100 m este de la antigua Bomba Delta) y servicios propios de "Hospital Básico" (cirugía general, parto normal, cesárea, urgencias 24 h). Pero ni Google ("Hospital Jerusalem") ni el sitio propio ("Clínica Jerusalén") usan el nombre oficial del censo ("Hospital Cristiano Jerusalén") como marca visible; ese nombre solo aparece en el usuario de Instagram.</td>
<td>clinicajerusalen.com: encabezado "Clínica Jerusalén, Hospital Básico"; menciona parto normal, cesárea y atención 24 horas. Snapshot y lectura en vivo: nombre_google "Hospital Jerusalem".</td>
<td>Ninguna acción urgente. El censo ya documenta bien el caso; solo tenerlo presente si alguien pregunta por el nombre.</td>
</tr>

<tr>
<td>Baja</td>
<td>hospital-clinica-santa-rita-san-jose (fuera del ranking este mes, 8 reseñas)</td>
<td>Google no le asigna categoría (categoria_google nulo) y el nombre en Google es "Clínica Santa Rita", sin la palabra "Hospital". El censo se apoya en un directorio de seguros (Bupa) y redes sociales, no en un sitio propio verificable: el dominio hospitalclinicasantaritacr.com devolvió error 403 al intentar confirmarlo. Sin impacto este mes por estar bajo el mínimo de 10 reseñas.</td>
<td>Snapshot: categoria_google null, sitio_web null. <code>data/ranking/2026-09.json</code>: motivo_exclusion "Menos de 10 reseñas (8)".</td>
<td>Confirmar servicios de internamiento con una fuente primaria antes de que cruce el umbral de 10 reseñas y entre al ranking.</td>
</tr>

<tr>
<td>Baja</td>
<td>hospital-metropolitano-cariari-belen</td>
<td>Calificación de 1.6 sobre 82 reseñas, muy por debajo de toda la red (la siguiente peor de todo el ranking es 2.2). La identidad cuadra (cid, dirección y categoría "Hospital" consistentes con el censo), así que no parece un error de datos, pero el contraste va a llamar la atención de cualquier lector.</td>
<td><code>data/ranking/2026-09.json</code>: posición 24, calificación 1.6, 82 reseñas.</td>
<td>Revisar reseñas recientes de esa sede para tener una explicación lista antes de publicar.</td>
</tr>

<tr>
<td>Baja</td>
<td>Sentido común, composición del ranking</td>
<td>10 de las 24 filas rankeadas (42%) son sedes de una misma marca, Hospital Metropolitano. No es un error, pero en la tabla publicada puede leerse como que un solo grupo domina el ranking en vez de competir hospital contra hospital.</td>
<td><code>data/ranking/2026-09.json</code>: posiciones 2, 3, 4, 6, 7, 13, 15, 17, 21 y 24 son sedes Metropolitano.</td>
<td>Sugerido: mostrar la columna "red" (ya existe en los datos) en la vista pública para que quede claro que son sedes de un mismo grupo.</td>
</tr>

<tr>
<td>Baja</td>
<td>data/hospitales.json, fuera del alcance privado</td>
<td>La entrada pública "Hospital San Juan de Dios" tiene <code>sitio_web</code> "https://www.hospigen.gob.gt/", un dominio de Guatemala, no de Costa Rica. No afecta el ranking de este mes porque <code>tipos_incluidos</code> en config.json solo trae "privado", pero es señal de que el campo sitio_web de los 30 públicos no se revisó a fondo.</td>
<td><code>data/hospitales.json</code>, entrada hospital-san-juan-de-dios.</td>
<td>Pasada de QA en sitio_web de los hospitales públicos antes de usarlos en cualquier publicación futura.</td>
</tr>

</table>

## Verificación en vivo de 8 perfiles

Los 8 se releyeron con `pipeline/gmaps.py ficha` entre las 23:40 y las 00:10 del 21 al 22 de setiembre, unas horas después del snapshot oficial (capturado 21 set, 23:15).

<table>
<tr><th>Hospital</th><th>Calificación snapshot</th><th>Calificación en vivo</th><th>Reseñas snapshot</th><th>Reseñas en vivo</th></tr>
<tr><td>Hospital Clínica Bíblica (San José)</td><td>4.6</td><td>4.6</td><td>2001</td><td>2001</td></tr>
<tr><td>Hospital CIMA</td><td>3.4</td><td>3.4</td><td>377</td><td>377</td></tr>
<tr><td>Hospital Metropolitano San Carlos</td><td>4.9</td><td>4.9</td><td>247</td><td>no disponible (Google no mostró el total en dos lecturas seguidas; la calificación sí coincidió las dos veces)</td></tr>
<tr><td>Hospital Internacional La Católica</td><td>3.5</td><td>3.5</td><td>307</td><td>307</td></tr>
<tr><td>Hospital Metropolitano Quepos</td><td>3.6</td><td>3.6</td><td>45</td><td>45</td></tr>
<tr><td>Hospital Jerusalem (Hospital Cristiano Jerusalén)</td><td>3.1</td><td>3.1</td><td>42</td><td>42</td></tr>
<tr><td>Hospital Clínica Señora de los Ángeles</td><td>3.0</td><td>3.0</td><td>122</td><td>122</td></tr>
<tr><td>Hospital Metropolitano Escazú</td><td>4.3</td><td>4.3</td><td>23</td><td>23</td></tr>
</table>

Ninguna calificación cambió. Las reseñas coincidieron de forma exacta en 7 de 8; en Metropolitano San Carlos la herramienta de lectura rápida no mostró el total en ninguno de los dos intentos (limitación de la lectura puntual, no una discrepancia: el snapshot sí lo obtuvo por la vía de respaldo que usa `capturar`).

## Reproducción del índice

Se escribió un script propio, independiente de `pipeline/score.py`, que recalcula desde cero `m`, `C`, calificación ajustada, puntaje de calificación, puntaje de volumen e índice para los 24 hospitales en ranking, usando `data/snapshots/2026-09.json`, `data/hospitales.json` y `config.json`.

Resultado: **desvío máximo encontrado = 0.0**. Los 24 índices, las 24 calificaciones ajustadas y las 24 posiciones coinciden exactamente con `data/ranking/2026-09.json` (m = 141.0 en ambos casos, C = 4.015 contra 4.0147 propio, diferencia de redondeo de visualización, no de cálculo). El conjunto de hospitales en ranking es idéntico (24 = 24). No se encontraron errores en la fórmula ni en su implementación.
