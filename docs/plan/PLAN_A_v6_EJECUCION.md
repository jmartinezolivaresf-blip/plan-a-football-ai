# Plan A v6: plan de ejecución en paralelo (2 personas, 4 días)

**Documento de referencia:** `PLAN_A_v6.md` (qué construimos). Este documento explica **cómo** lo construimos entre dos personas sin pisarnos.
**Horario:** hora peninsular. **Ojo:** el domingo 25 a las 03:00 el reloj se atrasa 1 h (la noche del sábado tiene una hora más).
**Plazo oficial:** martes 27, 23:59 PT = miércoles 28, 07:59 hora peninsular. **Objetivo interno: enviar el martes 27 antes de las 20:00.**

---

## 0. Calendario y supuestos

| Bloque | Cuándo | Para qué |
|---|---|---|
| **Arranque** (día 0) | Jueves 22, 19:00–22:30 | Contratos, fixtures, repo, Azure. **Sin esto no se puede trabajar en paralelo** |
| **Día 1** | Viernes 23 | Núcleos por separado: simulador (A) y servidor MCP + agentes contra el mock + esqueleto web (B) |
| **Día 2** | Sábado 24 | Primera integración real a las 13:00; un partido completo en local por la noche |
| **Día 3** | Domingo 25 | Duelo, evaluación y despliegue en Azure; URL pública por la noche |
| **Día 4** | Lunes 26 | Evaluación final, README, escritorio de analista, pulido; **congelación a las 22:00** |
| **Entrega** | Martes 27 | Solo bugs, vídeo y envío. **No se construye nada nuevo** |

**Jornada de trabajo supuesta:** unas 11 h por persona y día (10:00–14:00, 15:00–20:00, 21:00–23:00). Si es menos, se aplican antes los recortes del §9.

---

## 1. Principios

1. **Contratos primero.** El jueves se congelan los esquemas de datos y las firmas de las funciones y las herramientas. Después, cada uno trabaja contra los contratos, no contra el código del otro.
2. **El mock como puente.** B desarrolla agentes y UI contra un `mock_engine` que devuelve datos del fixture con la forma exacta de los contratos. El sábado a las 13:00 se cambia `ENGINE=mock` por `ENGINE=real`.
3. **Rebanadas verticales.** Cada noche hay algo que funciona de punta a punta, aunque sea feo. Un partido completo feo vale más que un simulador perfecto sin UI.
4. **Propiedad por carpetas.** Cada carpeta tiene dueño. En las del otro solo se entra con un PR que el dueño revisa.
5. **Regla de no bloqueo.** Si falta algo del otro, se usa el fixture y se sigue. Nadie espera más de 15 min sin avisar.
6. **Los hitos se respetan.** Si un hito falla a las 22:00, se aplica el recorte previsto (§9) **esa misma noche**, sin debatirlo.

---

## 2. Roles y propiedad

| | **Persona A: simulación y motor** | **Persona B: agentes y producto** |
|---|---|---|
| Carpetas propias | `sim/`, `sim/render/`, `engine/`, `eval/`, `data/` | `mcp_server/`, `agents/`, `agents/validators/`, `web/`, `infra/` |
| Carpetas compartidas | `contracts/`, `fixtures/`, `tests/`, `docs/` | Ídem |
| Responsable de | Simulador vectorizado, temporada, scouting, KPIs, valoración y duelo (`price_matrix`, lectura, arrepentimiento), evaluación E1–E8, calibración, búsqueda de semilla, capa visual | Servidor MCP con ámbitos, agentes y workflows (previa, directo, duelo, final), validadores, sellado, bundle, frontend, despliegue en Azure, trazas |
| Entregables para el otro | Funciones del motor con las firmas de `contracts/engine_api.md` | Herramientas MCP que llaman a esas funciones; UI que lee `match_bundle.json` |
| Dueño del README | Métodos, calibración, transparencia | Arquitectura, despliegue, cómo probarlo, uso de Copilot |

**Responsable del vídeo:** B monta y A revisa el guion y los números. **Responsable del envío:** quien sea el *Representative* del equipo en la plataforma (decidirlo el jueves).

---

## 3. Qué se congela el jueves (día 0)

### 3.1 Esquemas de datos (`contracts/*.schema.json`, con pydantic como fuente)
| Contrato | Dueño | Contenido mínimo |
|---|---|---|
| `events` | A | §9.1 de v6: `event_id, match_id, t, period, minute, possession_id, type, team, player_id, zone, x, y, end_x, end_y, receiver_id, outcome, under_pressure, body_part, set_piece_ref` |
| `snapshot` | A | marcador, minuto, cambios usados, jugadores en el campo, condición estimada, estado de los KPIs |
| `squads` | A | jugadores con atributos visibles 0–100 |
| `plan` | B | palancas, `lever_evidence`, KPIs, `plan_b`, `subs_plan`, `valuation`, `sealed` (Anexo B.1) |
| `option` | B | `option_id`, `label{en,es}`, cambios de palanca, cambios de jugador, `evidence[]` |
| `claim` | A + B | `claim_id, type, team, player_id?, metric, value, league_ref?, n, interval?, evidence[], status` y los tipos nuevos `sim_matrix_cell`, `opponent_estimate`, `regret` |
| `matrix` | A | `rows[option_id]`, `cols[option_id]`, `cells[i][j] = {xpts_kes, xpts_har, ci_kes, ci_har, claim_id}`, `reading{best_response[], safe, best_guess, gamble, dominant?}` |
| `cue` | B | §9.16 de v6 |
| `trace` | B | `agent, step, tool, args, result_claims[], duration_ms, status (ok/rejected/retried/fallback)` |
| `match_bundle` | B | `meta, squads, events[], snapshots[], render_frames[], plans[], duel{options, estimates, believed_matrices, choices, true_matrix, regret}, cues[], traces[], eval{}` |

### 3.2 API del simulador (`contracts/sim_api.md`, dueño A)
```python
def simulate(plans: dict[str, Plan], squads: Squads, seed: int, R: int = 1,
             log: bool = False, start: MatchState | None = None,
             until_minute: int = 90) -> SimResult: ...
# R=1 y log=True -> events[] y snapshots[] del partido; R>1 -> solo resultados agregados

def fork(state: MatchState, overrides: dict[str, Option], R: int, seed: int) -> Outcomes: ...
# overrides = {"KES": option, "HAR": option}; las mismas semillas para cualquier combinación de overrides
```

### 3.3 API del motor (`contracts/engine_api.md`, dueño A)
```python
get_team_tendencies(team, aspect) -> list[Claim]
get_player_profile(player_id) -> list[Claim]
get_set_piece_profile(team) -> list[Claim]
get_squad_condition(match_id, team, minute) -> list[Claim]
simulate_plan(plan, opponent_estimate, R) -> list[Claim]
estimate_opponent_options(match_id, team) -> OpponentOptionsEstimate   # opciones probables + probabilidades + claims
price_matrix(match_id, own_options, opponent_options, R, perspective) -> Matrix
true_matrix(match_id) -> Matrix                                        # solo ámbito broadcast, tras los sellos
regret(match_id) -> dict[str, Claim]
get_plan_status(match_id, team, minute) -> list[Claim]
get_match_state(match_id, minute) -> Snapshot
get_events(match_id, filter) -> list[Event]
get_claim(claim_id) -> Claim
```

### 3.4 Herramientas MCP (`contracts/tools.md`, dueño B)
Para cada herramienta: nombre, argumentos, ámbito permitido (`KES` / `HAR` / `broadcast`), función del motor a la que llama y qué devuelve. Lista de §9.13 de v6, más `validate_plan` y `seal_choice`.

### 3.5 Fixtures (`fixtures/`)
| Fixture | Dueño | Contenido |
|---|---|---|
| `match_fixture.json` | A | Unos 300 eventos de un partido falso con coherencia básica + snapshots cada minuto |
| `squads_fixture.json` | A | 2 plantillas de 18 |
| `plans_fixture.json` | B | Los dos planes del §7.1 de v6 |
| `duel_fixture.json` | B | Las opciones, las estimaciones, las 3 matrices y el arrepentimiento del §7.3 / §7.4 de v6 (números coherentes) |
| `tools_canned/*.json` | B | Una respuesta de ejemplo por herramienta |

**Regla:** el fixture se valida contra los esquemas en CI. Si cambia un contrato, el fixture cambia en el mismo PR.

---

## 4. Puntos de integración

| ID | Cuándo | Qué se conecta | Prueba de que funciona |
|---|---|---|---|
| **I0** | Jue 22, 22:30 | Contratos + fixtures en `main` | La CI valida los fixtures contra los esquemas; un modelo responde desde Foundry |
| **I1** | Sáb 24, 13:00 | El servidor MCP pasa de `mock_engine` al motor real | La previa corre con los datos reales de la temporada |
| **I2** | Sáb 24, 22:00 | Pipeline completo en local → `match_bundle.json` → web | Un partido de punta a punta en el navegador |
| **I3** | Dom 25, 22:00 | Bundle con el duelo + despliegue en Azure | URL pública con el duelo funcionando |
| **I4** | Lun 26, 22:00 | Bundle final congelado (semilla elegida) + evaluación en `test` | Congelación de funcionalidades |

---

## 5. Plan detallado por día

### Jueves 22: arranque (19:00–22:30, los dos)
| Hora | Persona A | Persona B |
|---|---|---|
| 19:00–19:30 | **Juntos:** leer §00, §7 y §9 de v6; confirmar roles, *Representative* y categoría provisional | |
| 19:30–21:00 | Contratos `events`, `snapshot`, `squads`, `matrix`, `sim_api.md`, `engine_api.md` · repo + estructura de carpetas + CI con pytest y validación de esquemas | Contratos `plan`, `option`, `cue`, `trace`, `match_bundle`, `tools.md` · **Azure día 0:** grupo de recursos, proyecto de Foundry, despliegue de 2 modelos, **comprobación de cuota**, App Insights |
| 21:00–21:30 | **Revisión cruzada de contratos** (cada uno revisa los del otro) · `claim` entre los dos | |
| 21:30–22:30 | `match_fixture.json`, `squads_fixture.json` | `plans_fixture.json`, `duel_fixture.json`, `tools_canned/` · fijar las versiones de Agent Framework y del SDK de MCP |
| **22:30** | **I0** | |

**Si la cuota de Foundry no está:** B lo documenta en `docs/DECISIONS.md` y se elige un modelo de respaldo esa misma noche.

### Viernes 23: día 1, núcleos en paralelo
| Hora | Persona A: simulador | Persona B: MCP, agentes, web |
|---|---|---|
| 10:00 | **Sincronización (15 min)** | |
| 10:00–14:00 | Simulador vectorizado: arrays de estado `(R,)` y `(R, 22)`, 18 zonas, softmax de acciones, logit de éxito, pérdidas, reloj, máscara de réplicas terminadas · esquema de semillas por (réplica, paso, uso) para los números aleatorios comunes · ruta `R=1, log=True` | Servidor MCP (SDK de Python, HTTP en streaming) + `mock_engine` sobre fixtures · cabecera `X-Team-Scope` (KES / HAR / broadcast) · **tests de ámbito**, incluido que `get_true_matrix` está bloqueado para los cuerpos técnicos y antes de los sellos |
| 15:00–18:00 | Tiros y goles internos, micro-modelo de córner, fatiga, cambios (5 en 3 ventanas + descanso), disparadores del Plan B, 5 palancas | Agent Framework: **analista y míster de la previa contra el mock** · salidas con esquema pydantic · `validate_plan` v1 · sellado (SHA-256 del JSON canónico) |
| 18:00–20:00 | **Tests de invariantes** (continuidad de la posesión, marcador = goles, límites de cambios, determinismo por semilla, misma semilla → mismo resultado con `R=1` y en la réplica correspondiente de `R>1`) · **medición de rendimiento** | Web: Vite + React + TS, cargador del bundle, reloj de reproducción, `Pitch2D` (balón y puntos desde el fixture), `Scorebug`, `PlanCard`, `SealBadge` |
| 21:00–22:00 | `fork(state, overrides)` desde el snapshot del descanso · prueba rápida: goles y tiros por partido en rango | Verificador de textos (marcadores, claims por frase, verbos causales) + plantilla de respaldo · captura de trazas (`trace`) |
| **22:00** | **Sincronización + H1:** 90' simulados desde dos planes, invariantes en verde, rendimiento medido · un míster genera un plan válido contra el mock | |

**Criterio de H1 para el rendimiento:** con `R=500`, una segunda parte en ≤ 1 s. Si no se llega, se aplica el recorte H1 (§9).

### Sábado 24: día 2, primera integración
| Hora | Persona A: motor | Persona B: workflows, cues |
|---|---|---|
| 10:00 | **Sincronización** | |
| 10:00–13:00 | 6 equipos con arquetipos y **rasgos ocultos** (catálogo de §9.4 de v6) · temporada de 8 partidos por equipo exportada al contrato · `truth` y `sim_config` aparte · modelo de xG del motor | **WF-Previa completo:** los dos equipos en paralelo y aislados, analista → míster, reintentos del validador, plantilla de respaldo, sellado en el registro |
| **13:00** | **I1, juntos (30–45 min):** `ENGINE=real` en el servidor MCP; arreglar diferencias de contrato. A expone el scouting aunque esté incompleto | |
| 13:45–17:00 | 4 funciones de scouting + `fade_profile` → claims con `n`, media de la liga y `insufficient` · Plan Tracker (4 KPIs, trayectoria esperada, histéresis) · detección de adaptación (saques de puerta y balones largos) | **WF-Directo:** bucle de disparadores → realizador (con límite de llamadas) → verificador → localizador → cues · prioridad, `ttl` y sin solapes |
| 17:00–20:00 | `simulate_plan` · **`price_matrix`** (vectorizado: celdas × R, mismas semillas en todas las celdas) · lectura (mejor respuesta, *safe*, *best guess*, *gamble*, dominante) · arrepentimiento · `estimate_opponent_options` (reglas deterministas) | Web: `PlanTrackerLT`, `AlertCue`, renderizador de cues sincronizado con el reloj |
| 21:00–22:00 | **Test de interés del duelo** en `dev`: en ≥ 50 % de los descansos, la mejor respuesta depende de la opción del rival; si no, ajustar las interacciones | **`make bundle`:** script que ejecuta todo el pipeline para un partido → `match_bundle.json` → carga en la web |
| **22:00** | **Sincronización + H2 / I2:** un partido de punta a punta en local (planes → simulación → KPIs → cues → UI) | |

### Domingo 25: día 3, duelo y despliegue
*(La noche del sábado al domingo tiene una hora más: buena para dormir, no para trabajar.)*

| Hora | Persona A: evaluación y demo | Persona B: duelo y Azure |
|---|---|---|
| 10:00 | **Sincronización** | |
| 10:00–13:00 | **E1, E2, E3** sobre `dev` → congelar umbrales · arnés de **E7** (anticipación) y **E8** (arrepentimiento frente a "no tocar nada" y "al azar") con N descansos | **WF-Duelo:** los dos equipos en paralelo → revisión del analista → `estimate_opponent_options` (+ ajuste acotado del LLM) → `price_matrix` → elección con regla → `seal_choice` → **barrera** → revelación → `true_matrix` → cues del duelo · caso de fallo guionizado (cambio inválido → rechazado → rehecho) |
| 13:00–16:00 | Tabla de calibración sobre la temporada · ajuste de coeficientes · invariantes completos | `DuelRooms`, **`DuelMatrix`**, `RegretCard` · **prueba de lectura**: enseñar la matriz 15 s a alguien ajeno al proyecto |
| 16:00–19:00 | **Búsqueda de semilla** para la historia de la demo, con criterios escritos (KES pierde al descanso, HAR se adapta antes del 35', duelo no dominante, final verosímil) · script y resultado en `docs/` | **Despliegue en Azure:** imagen del servidor MCP → Container Apps (réplica mínima 1) · web + bundle → Static Web Apps · trazas a App Insights · alerta de presupuesto |
| 19:00–21:00 | Capa visual: posiciones del partido de la demo a partir de las zonas y las palancas activas, con los invariantes visuales | Smoke test de la URL pública en modo incógnito · arreglos del despliegue |
| 21:00–22:00 | Regenerar el bundle con la semilla elegida y la capa visual → entregárselo a B | Integrar el bundle nuevo en el despliegue |
| **22:00** | **Sincronización + H3 / I3:** URL pública con el duelo · **decisión de categoría** (*Multi-Agent* o *Foundry*) | |

### Lunes 26: día 4, cierre de funcionalidades
| Hora | Persona A | Persona B |
|---|---|---|
| 10:00 | **Sincronización** | |
| 10:00–13:00 | **Evaluación final en `test`** (E1, E2, E3, E7, E8) → `eval/results/*.json` para el panel de validación | Cronista + cues de arrepentimiento + pantalla final · localizador EN/ES × aficionado/analista |
| 13:00–17:00 | README: métodos, calibración (con **fuentes revisadas**), transparencia (§11 de v6), cómo ejecutarlo · `docs/ARCHITECTURE` | Escritorio `/analyst`: `AgentTrace`, `ValidationPanel`, enlaces a evidencias, interruptor "matriz creída / real" · `Settings` (modo, club, idioma) · exportar la cue sheet |
| 17:00–20:00 | Bugs · determinismo del bundle (dos ejecuciones dan lo mismo) · **bundle final congelado** | Pulido de UX y de textos (aficionado / analista) · comprobar trazas · `docs/COPILOT_USAGE.md` |
| 20:00–22:00 | **Juntos:** ensayo cronometrado del guion del vídeo (§14 de v6), lista de planos, texto de la voz | |
| **22:00** | **H4 / I4: congelación de funcionalidades.** A partir de aquí, solo bugs | |

### Martes 27: entrega
| Hora | Persona A | Persona B |
|---|---|---|
| 10:00–12:00 | Bugs críticos · repasar números del README frente al panel | Bugs críticos · despliegue final · smoke test en incógnito (§10) |
| 12:00–15:00 | Voz y revisión de los números que salen en el vídeo | **Grabación** de pantalla a 1080p según la lista de planos |
| 15:00–17:30 | Pitch y texto de entrega (qué hemos construido, tecnologías de Microsoft, qué hace, qué problema resuelve) · instrucciones de prueba | **Montaje** (< 2 min, cronometrado) · subtítulos EN · subida pública a YouTube o Vimeo |
| 17:30–19:00 | **Juntos:** checklist de entrega (§11), repo público, enlaces, categoría | |
| **19:00–20:00** | **Envío** y comprobación de que la entrega aparece en la plataforma | |

---

## 6. Rutina diaria

**10:00 sincronización (15 min):**
- Qué terminé ayer (con enlace al PR).
- Qué hago hoy (en las filas del §5).
- Qué necesito del otro y para cuándo.
- ¿Algún cambio de contrato? (Si lo hay, se hace en ese momento.)

**22:00 sincronización (20–30 min):**
- ¿Se cumple el hito? Sí o no, sin matices.
- Si no se cumple: se aplica el recorte del §9 y se anota en `docs/DECISIONS.md`.
- Integración de lo del día en `main`.
- Riesgos para mañana.

**Canal asíncrono:** un único chat con tres tipos de mensaje: `BLOQUEO:`, `CONTRATO:` y `HECHO:`. Un `BLOQUEO` se responde en ≤ 15 min o se aplica la regla de no bloqueo.

---

## 7. Git y CI

- **`main` siempre verde.** Ramas cortas (`a/sim-core`, `b/mcp-scope`), PRs de menos de un día.
- **Revisión:** cada PR que toque carpetas del otro lo revisa el dueño. Los PRs dentro de las carpetas propias pueden fusionarse con CI verde sin esperar revisión (se revisan en la sincronización).
- **Cambios de contrato:** PR con la etiqueta `contract` que actualiza a la vez el esquema, los fixtures, el mock y los tests. **Lo aprueban los dos.** Se anota en `docs/DECISIONS.md`.
- **La CI ejecuta en cada PR:**
  - validación de los fixtures contra los esquemas;
  - invariantes del simulador y determinismo;
  - separación de información (ámbitos, `get_true_matrix`, el motor no lee `truth`/`sim_config`);
  - sellado (hash verificable);
  - verificador de textos sobre los textos del bundle;
  - tests del frontend que haya (`npm test`).
- **Ficheros generados:** `data/` en `.gitignore`, salvo el `match_bundle.json` de la demo.

---

## 8. Asistentes de código en paralelo

Cada persona puede llevar **2 sesiones** de asistente (GitHub Copilot en modo agente u otro), cada una con su carpeta y su tarea. Reglas:

| Sesión | Carpeta | Ejemplo de tarea |
|---|---|---|
| A-1 | `sim/` | "Implementa `simulate()` vectorizado según `contracts/sim_api.md`; tests en `tests/test_sim_*.py`" |
| A-2 | `engine/`, `eval/` | "Implementa `get_team_tendencies` según `contracts/engine_api.md`, devolviendo claims válidos según `claim.schema.json`" |
| B-1 | `mcp_server/`, `agents/` | "Expón las herramientas de `contracts/tools.md` con el filtro de ámbito; tests de ámbito" |
| B-2 | `web/` | "Componente `DuelMatrix` que lee `duel.true_matrix` del bundle según `match_bundle.schema.json`" |

- **Los contratos son de solo lectura para los asistentes.** Si un asistente necesita cambiarlos, para y lo propone la persona.
- **Tests primero:** cada tarea le pide al asistente los tests junto al código.
- **Revisión humana** de todo lo que entra en `main`, sobre todo en `sim/` (los números) y en la separación de información.
- El uso de Copilot se anota sobre la marcha en `docs/COPILOT_USAGE.md` (cuenta como tecnología estrella).

---

## 9. Recortes por hito (se aplican esa misma noche)

| Si falla… | Recorte | Quién | Impacto en la demo |
|---|---|---|---|
| **H1** (vie): el simulador no juega 90' o es lento | Se quita `corner_delivery`; fatiga lineal fija; `R=300`; todo lo de la demo, precalculado | A | Casi nulo |
| **H1** (vie): el míster no da planes válidos | Esquema más estricto + plantilla por arquetipo; el LLM solo elige entre plantillas y justifica con claims | B | Bajo |
| **H2** (sáb): no hay partido de punta a punta | El realizador pasa a plantillas sin LLM; el informe del analista se precalcula | B | Medio (menos LLM en directo) |
| **H2** (sáb): el duelo no da historias (una opción domina siempre) | Ajustar las interacciones en `dev` el domingo por la mañana; si sigue igual, se anuncia como *"dominant move"* | A | Bajo |
| **H3** (dom): el duelo 3 × 3 no está | Duelo **2 × 2** (*Stay* + una alternativa); la estimación del rival, solo determinista | A + B | Medio |
| **H3** (dom): el duelo no está de ninguna forma | Valoración de un solo banquillo (v5) | A + B | Alto (se pierde el diferencial) |
| **H3** (dom): Azure falla | Web estática en Static Web Apps con el bundle; el servidor MCP en local para el vídeo, documentado | B | Bajo para el vídeo, medio para los jueces |
| **H4** (lun): no da tiempo a todo | Solo EN; crónica sencilla; el escritorio de analista con el rastro y el panel de validación, sin más | B | Bajo |

**Lo que nunca se recorta:** separación de información (con tests), sellado, cero cifras del LLM, E1 y el vídeo de menos de 2 min.

---

## 10. Runbooks

### 10.1 Azure (jueves, B, máximo 2 h)
1. Grupo de recursos en una región con los modelos necesarios.
2. Proyecto de Microsoft Foundry → desplegar un modelo mayor y uno pequeño → **comprobar la cuota** → probar una llamada.
3. Application Insights conectado al proyecto de Foundry.
4. Container Apps Environment (vacío) y Static Web Apps (vacío).
5. Alerta de presupuesto.
6. Secretos y variables en un `.env.example` (nunca claves en el repo); identidad gestionada donde se pueda.

### 10.2 `make bundle` (sábado, B con funciones de A)
```
make season      # A: genera la temporada (6 equipos × 8 partidos) + truth + sim_config
make prematch    # B: WF-Previa para KES y HAR → planes sellados
make match       # A: simulate(R=1, log=True) primera parte → snapshot del descanso
make duel        # B: WF-Duelo → elecciones selladas → true_matrix (A)
make second-half # A: simulate desde el descanso con las dos elecciones
make live        # B: WF-Directo sobre los eventos → cues
make final       # B: WF-Final → crónica + arrepentimiento
make render      # A: capa visual
make eval        # A: E1–E8 → eval/results
make bundle      # B: lo junta todo en web/public/match_bundle.json y valida el esquema
```

### 10.3 Smoke test de la URL pública (domingo y martes)
- [ ] Carga en una ventana de incógnito, sin login.
- [ ] Se reproduce el partido completo: previa → directo → duelo → final.
- [ ] Modo aficionado y analista, EN y ES, cambio de club favorito.
- [ ] El escritorio de analista enseña el rastro y el panel de validación.
- [ ] La cue sheet se exporta.
- [ ] El servidor MCP responde (o la demo funciona sin él).
- [ ] Tiempo de carga razonable.

---

## 11. Checklist de entrega (martes)

- [ ] Repo de GitHub **público**, con README completo y licencia.
- [ ] Vídeo **< 2 min**, público en YouTube o Vimeo, sin marcas ni música de terceros, con subtítulos EN.
- [ ] Pitch: qué hemos construido, tecnologías de Microsoft, qué hace, qué problema resuelve.
- [ ] Categoría declarada.
- [ ] URL de la demo + instrucciones de prueba.
- [ ] Todo en inglés.
- [ ] Despliegue configurado para seguir disponible **hasta el 10 nov** (réplica mínima 1, presupuesto vigilado).
- [ ] Sin código de otros participantes; dependencias con licencia compatible.
- [ ] Los números del vídeo, del README y del panel de validación coinciden.

---

## 12. Grafo de dependencias

```
JUE  contracts ──┬──────────────────────────────┬───────────────────────┐
                 │                              │                       │
VIE        sim vectorizado (A)          mock_engine + MCP (B)     web esqueleto (B)
                 │                              │                       │
                 │                       agentes previa (mock)          │
SÁB   season + traits + scouting (A) ──▶ I1: MCP real ──▶ WF-Previa     │
                 │                              │                       │
           KPIs + adaptación (A) ───────▶ WF-Directo + cues (B) ──▶ make bundle ──▶ I2
                 │                                                      │
           price_matrix + regret (A) ──────────────┐                    │
DOM        eval E1–E3, E7, E8 (A)          WF-Duelo (B) ──▶ DuelMatrix ─┤
           seed search + render (A) ───────────────┴──▶ bundle ──▶ Azure ──▶ I3
LUN        eval test + README (A)          final + /analyst + pulido (B) ──▶ I4
MAR                        vídeo + envío (A + B)
```

**Ruta crítica:** `contracts → sim vectorizado → price_matrix → WF-Duelo → DuelMatrix → bundle → vídeo`.
**Por qué no bloquea:** el `duel_fixture.json` permite a B construir el duelo completo y la `DuelMatrix` desde el viernes, sin esperar a `price_matrix`.

---

## 13. Plantillas

**`docs/DECISIONS.md`**
```
## 2026-10-24 22:10 · H2 · decisión
Contexto: el realizador LLM tarda 9 s por cue.
Decisión: límite de 1 llamada por disparador; plantillas para las alertas de KPI.
Impacto: ninguno visible en la demo.
Quién: A + B
```

**Descripción de PR**
```
Qué: …
Contrato tocado: no / sí (etiqueta `contract`)
Tests: …
Cómo probarlo: …
```

**Mensaje de bloqueo**
```
BLOQUEO: necesito `price_matrix` con perspective="HAR" para el duelo. Hasta entonces uso duel_fixture. ¿Hora estimada?
```
