# Plan A (v6, el duelo de banquillos): informe de proyecto

**Hackathon:** Microsoft + Premier League · Inside the Game: Developer Hackathon
**Reto:** The Synthetic Match Insights Engine for Premier League Studio
**Entrega:** martes 27 oct 2026, 23:59 PT = **miércoles 28 oct, 07:59 hora peninsular**. Objetivo interno: **enviar el martes 27 antes de las 20:00**.
**Equipo:** 2 personas · **Categoría:** *Best Multi-Agent System* (decisión final el domingo 25; alternativa: *Best Use of Microsoft Foundry*)
**Origen:** evolución de `PLAN_A_v5.md` (recorte de `PLAN_A_INFORME.md` v4, que pivota desde *Tactical Twin v3.1*).

> *"Every manager has a Plan A. The other manager has an answer. We show both, and what each guess was worth."*

**Pregunta central:** *¿Qué plan trae cada entrenador contra este rival concreto, está funcionando y, cuando los dos banquillos ajustan a la vez, qué decisión resiste mejor la respuesta del otro?*

---

## 00. Qué cambia en la v6: el duelo de banquillos

En la v5, el descanso valoraba las opciones de **un solo equipo** frente a "no tocar nada", **suponiendo que el rival no reacciona** (salvo su Plan B guionizado). Es la misma suposición que hace *The Dugout*, y en el fútbol real no se cumple.

**La v6 convierte el descanso en un duelo simultáneo:**
1. Cada cuerpo técnico propone **3 opciones** (la primera siempre es *Stay the course*) **sin ver las del rival**.
2. El analista de cada equipo **estima las 3 opciones más probables del rival**, con probabilidades, a partir de claims.
3. Cada míster decide con su **matriz creída** (sus opciones × las opciones estimadas del rival) y elige entre *safe pick* y *gamble*.
4. Las dos elecciones se **sellan** y después se revelan.
5. El motor juega la **matriz real 3 × 3** (opciones reales de KES × opciones reales de HAR), con las mismas semillas, para la retransmisión.
6. Al final, el **arrepentimiento** de cada banquillo: cuánto habría ganado con la mejor respuesta a lo que el rival hizo de verdad.

El resultado es que **cada decisión se valora contra la respuesta del rival, no contra un rival pasivo**. Además, el multi-agente deja de ser una elección de diseño y pasa a ser **imprescindible**: un solo agente vería las dos opciones y el duelo no existiría.

Secciones afectadas: §0, §1, §3, §4, §5, §6, §7.3, §7.4, §8, §9.9 (nueva valoración), §9.11, §9.13, §9.15, §9.16, §11, §13, §14, §15, §16.

---

## 0. Qué cambia respecto a la v4 y por qué

La v4 tiene la mejor idea del proceso, pero con dos problemas:

1. **Alcance de unas 3 veces el de Tactical Twin v3.1** para 5,5 días: 12 palancas, 12–16 clubes, 9 funciones de scouting, 16 herramientas MCP, 11 instancias de agentes en 4 workflows, IaC, agente hospedado…
2. **Solapamiento con *The Dugout*** (`lauramiro/the-dugout`, verificado el 22 oct: 122 commits desde el 19 oct, desplegado, servidor MCP público). Comparte con la v4 la capa de retransmisión casi entera: ΔWP con intervalo y etiquetas *strong / lean / toss-up*, voto de fans de 20 s antes de revelar, vista 16:9 + `/desk`, curva de WP, cue sheet exportable, bifurcación contra la verdad, búsqueda de semilla, *What if* final y el gancho NFL / F1.

**La v5:**
- **Recorta** a un núcleo que se puede terminar con calidad (§6).
- **Centra el proyecto en lo que *The Dugout* no tiene:** la previa con **scouting contra rasgos ocultos**, **dos cuerpos técnicos con información privada** y **planes sellados**.
- **Se diferencia a propósito** en la capa de retransmisión: puntos esperados (xPts) en lugar de WP, etiquetas propias, sin gancho NFL / F1, y el voto de fans pasa a ser opcional (§3).
- **Diseña el simulador vectorizado sobre las réplicas desde el primer día**, porque la v4 confiaba en un bucle de Python que no llega al rendimiento necesario (§9.2).

**La v6** mantiene todo lo anterior y añade el **duelo de banquillos** en el descanso (§00).

---

## 1. Resumen

Plan A es un **sistema multi-agente que cuenta el partido como un duelo de planes de juego**, en cuatro momentos de retransmisión:

1. **Previa: "Sealed Plans".** Cada club tiene un cuerpo técnico de agentes (**analista + míster**) que, aislado del rival, estudia su historial sintético, descubre sus debilidades (que el sistema conoce como verdad oculta) y redacta un **plan de partido** con palancas tácticas, KPIs medibles y un Plan B condicionado. El míster **valora** los planes candidatos con simulaciones y elige uno. Los dos planes se **sellan** (SHA-256 publicado antes de simular el partido).
2. **Directo: "Plan Tracker".** El motor sigue los KPIs de cada plan, detecta con eventos cuándo el rival se adapta y genera overlays: *"KES · Squeeze the left-back — on track · 4 high turnovers (target 6 by HT)"*.
3. **Descanso: "The Duel".** Los dos cuerpos técnicos ajustan **a la vez y a ciegas**. Cada uno propone 3 opciones, su analista estima qué hará el rival y el míster elige con su matriz creída (*safe pick* o *gamble*). Las dos elecciones se sellan y se revelan. La retransmisión enseña la **matriz real 3 × 3** en **puntos esperados (ΔxPts)**, con la segunda parte bifurcada desde el estado exacto del descanso y las mismas semillas: *"KES's best move depends on HAR: if HAR goes long, the mid-block wins; if HAR keeps playing short, the press wins."*
4. **Final: "Whose plan won?".** Balance de cada plan, crónica verificada y el **arrepentimiento de cada banquillo**: *"KES's safe pick left 0.05 xPts on the table: HAR parked the bus, and the double attacking sub was the answer."*

Todo sale como **cues de overlay con marca de tiempo**, en modo aficionado o analista, EN/ES y desde la perspectiva del club favorito.

**Transparencia:** los datos son sintéticos y los clubes y jugadores, ficticios. Las interacciones tácticas del simulador son **reglas nuestras**, inspiradas en la práctica real y calibradas con promedios públicos. **No** afirmamos qué tácticas funcionan en la Premier League real. Lo que demostramos es que **los agentes descubren las debilidades ocultas solo con eventos, anticipan al rival y toman decisiones coherentes con la evidencia**, y eso sí lo medimos (§11).

---

## 2. Qué se reutiliza de Tactical Twin v3.1

| Pieza de v3.1 | En Plan A v6 |
|---|---|
| Contrato de datos (105×68 m absolutos, dirección por parte, `events`, `match_meta`) | Igual, ampliado con `squads`, `plan`, `snapshot`, `cue`, `claim` |
| Separación `truth` / `sim_config` + test "el motor no lee la verdad" | Igual, y además **separación entre cuerpos técnicos** (con test) |
| Claims con identificador, marcadores `{c7.x}`, validador en código, "evidencia insuficiente" | Igual: núcleo de confianza |
| Hecho frente a interpretación (causas solo con un claim de mecanismo) | Igual |
| Tests de invariantes y tabla de calibración con fuentes | Igual, adaptados al simulador por zonas |
| `dev` / `test` con parámetros distintos | Igual: equipos `test` con otros arquetipos y rasgos |
| Agent Framework + Foundry + herramientas por MCP + rastro visible | Ampliado a varios roles |
| Campo 2D, formas ancladas al balón | **Solo como capa visual** del partido de la demo (no es análisis, §9.8) |
| Detector de formaciones y cadenas tácticas | **Fuera** |

---

## 3. Diferenciación

### 3.1 Frente al campo general (lo que hace casi todo el mundo)
| Habitual | Plan A |
|---|---|
| Narrar lo que ha pasado | Explicar **lo que cada entrenador intenta** y si le sale |
| Multi-agente como cadena narrador → verificador → traductor | **Dos cuerpos técnicos con información privada** que se enfrentan |
| Datos sintéticos "calibrados" sin más | **Rasgos ocultos** que el scouting tiene que descubrir, con medición de precisión y recall |
| *What-if* a nivel de jugador | *What-if* a nivel de **plan de equipo** |

### 3.2 Frente a *The Dugout* (el competidor más cercano y más avanzado)
| *The Dugout* | Plan A v6 |
|---|---|
| Valora cada opción **frente a un rival pasivo** (opción contra no tocar nada) | Valora cada opción **frente a la respuesta del rival**: matriz 3 × 3, mejor respuesta, *safe pick* / *gamble*, arrepentimiento |
| Decide un solo banquillo | **Los dos banquillos deciden a la vez y a ciegas**, y las elecciones se sellan |
| Decisión en el partido: **sustituciones** | Decisión **antes** del partido (plan contra un rival concreto) + duelo en el descanso (los cambios son un tipo de opción más) |
| No hay scouting del rival | **Scouting a partir del historial, medido contra la verdad oculta** |
| Un flujo narrador → verificación → localizador | **Cuerpos técnicos rivales con información privada**, traspasos analista ↔ míster, planes sellados |
| ΔWP con *strong / lean / toss-up* | **ΔxPts** (puntos esperados, más propio del fútbol) con etiquetas *Clear gain / Marginal / Within noise* |
| Voto de fans como pilar | Voto de fans **opcional** |
| Gancho NFL / F1 | Gancho: **"the other manager has an answer"**, el duelo y los planes sellados |

**Regla:** no reutilizamos código, textos ni interfaz de *The Dugout* ni de ningún otro participante (las bases exigen obra original), aunque tenga licencia MIT. Las ideas generales (valorar decisiones con simulación, bifurcar contra la verdad, demo sin backend) son práctica estándar. En el pitch decimos explícitamente: *"every decision is priced against the other bench's answer, not against a passive opponent."*

---

## 4. Encaje con los criterios oficiales (20 % cada uno)

**Desempate:** primero Implementación tecnológica y después Diseño agéntico. La **fase 1 es eliminatoria**: hay que encajar en el tema (inteligencia explicable para estudio o retransmisión) y usar las tecnologías requeridas. Por eso Plan A se presenta como **experiencia de retransmisión**, no como herramienta de club.

| Criterio | Cómo lo cubrimos |
|---|---|
| **Implementación tecnológica** | Simulador por zonas **vectorizado** con palancas, fatiga y córners; temporada sintética con rasgos ocultos (*optimized synthetic data creation*); bifurcaciones con números aleatorios comunes; invariantes, calibración y evaluación frente a la verdad. Foundry, Agent Framework, MCP, Container Apps, Static Web Apps, GitHub Copilot |
| **Diseño agéntico e innovación** | **Agentes adversarios con información privada que se anticipan entre sí:** cada analista modela al otro banquillo y cada míster decide bajo incertidumbre (*safe pick* frente a *gamble*). Traspasos analista → míster; bucle de revisión; elecciones selladas; validador que rechaza y obliga a rehacer (recuperación de fallos visible); herramientas MCP con ámbito por equipo |
| **Impacto y aplicabilidad** | Formato nuevo para la tele de fútbol: enseñar los planes, cómo responde cada banquillo al otro y cuánto valía cada lectura. El mismo motor sirve a un club para preparar al rival y el descanso. El contrato admite el feed de un proveedor real |
| **UX y presentación** | Cuatro momentos de retransmisión reconocibles (previa, directo, duelo, final) + escritorio de analista con el rastro de los agentes; la matriz del duelo se lee en 15 s; vídeo de unos 110 s construido sobre una historia |
| **Adecuación a la categoría** (*Multi-Agent*) | Roles distintos, estado compartido (registro del partido), traspasos, recuperación de fallos y un resultado que **un solo agente no puede lograr**: si viera las dos opciones, no habría duelo ni anticipación |

---

## 5. Objetivos medibles (conjunto `test`)

| # | Objetivo | Métrica |
|---|---|---|
| O1 | **Scouting útil** (titular) | Precisión ≥ 70 % y recall ≥ 70 % de los rasgos ocultos del rival señalados en el informe |
| O2 | **Valoración estable** | Signo del ΔxPts estable ≥ 80 % y error absoluto medio ≤ 0,05 xPts, con n = 300 frente a una referencia con n = 3.000. **Mide el ruido del Monte Carlo, no la validez del modelo**, y lo diremos así |
| O3 | **Decisiones coherentes con la evidencia** | En el ≥ 80 % de los planes, cada palanca no por defecto cita un claim de scouting que la justifica |
| O4 | **Cero cifras del LLM** | 100 % de cifras desde marcadores; validación a la primera ≥ 85 %; 100 % tras regenerar o usar la plantilla |
| O5 | **Planes válidos** | 100 % de planes publicados pasan el validador; se reporta la tasa de revisiones |
| O6 | **Realismo** | ≥ 8 de 10 métricas de calibración dentro de rango |
| O7 | **Trazabilidad** | Desde cualquier overlay se llega a su evidencia en un clic |
| O8 | **Anticipación del rival** | En los descansos de `test`, la opción que el rival elige de verdad recibe en la estimación del analista una probabilidad media ≥ 0,45 (frente a 0,33 de un reparto uniforme) |
| O9 | **Decidir mejor que lo ingenuo** | Arrepentimiento medio del míster IA en `test` menor que el de dos referencias: "no tocar nada siempre" y "elegir al azar entre sus 3 opciones". Se reporta lo que salga, con intervalo |

---

## 6. Alcance

### 6.1 Imprescindible
| # | Funcionalidad |
|---|---|
| 1 | Contratos: `events`, `snapshot`, `squads`, `plan`, `claim`, `cue`, `truth`/`sim_config` + firma de `simulate()` y `fork()` |
| 2 | Simulador por zonas **vectorizado sobre réplicas**: 5 palancas, fatiga simple, micro-modelo de córner, cambios, Plan B; determinista por semilla; invariantes |
| 3 | 6 clubes ficticios con 3 rasgos ocultos cada uno; temporada de 8 partidos por equipo |
| 4 | 4 funciones de scouting con `n` y comparación con la liga |
| 5 | Plan Tracker con 4 KPIs y **una** detección de adaptación del rival |
| 6 | Valoración: `simulate_plan` (previa) y **`price_matrix`** (descanso: matriz 3 × 3 creída por cada banquillo y matriz real para la retransmisión) en ΔxPts con intervalo; mejor respuesta, *safe pick* / *gamble* y arrepentimiento |
| 7 | Servidor MCP con unas 10 herramientas y ámbito por equipo (con test) |
| 8 | Agentes: analista + míster por equipo (aislados), realizador, cronista y localizador |
| 9 | Workflows: previa, directo (determinista + realizador), **duelo del descanso (los dos equipos en paralelo, a ciegas)**, final |
| 10 | Validador de planes + verificador de textos + sellado de planes **y de elecciones del descanso** |
| 11 | Frontend: retransmisión (previa, directo, duelo con `DuelMatrix`, final) + escritorio de analista con rastro y panel de validación |
| 12 | Evaluación E1–E4 + **E7 (anticipación) y E8 (arrepentimiento frente a referencias)** + calibración, visible en la app |
| 13 | Despliegue en Azure (URL pública), trazas de agentes |

### 6.2 Versión sencilla
- Personalización: aficionado / analista, club favorito, EN/ES.
- **Un** fallo con recuperación visible (cambio inválido rechazado → rehecho).
- Cue sheet exportable (JSON).

### 6.3 Solo si sobra tiempo (por este orden)
1. Voto de fans *"Your pick"* en el duelo: el público elige por un banquillo y al final se ve su arrepentimiento frente al del míster IA.
2. Evaluaciones de Foundry sobre los agentes (E5).
3. Modo analista avanzado del duelo: equilibrio con estrategias mixtas (nunca en la vista de aficionado).
4. Más palancas (`defensive_line`, `width`, `tempo`).
5. *Ask the staff*: preguntas libres al míster.

### 6.4 Fuera del alcance
Agente hospedado en Foundry, Bicep/IaC completo, Cosmos DB, A2A, chat de grupo con más de 2 participantes, agentes propios de balón parado y de preparador físico (se convierten en **herramientas** del míster), 12–16 clubes, curva de WP por minuto como pilar, detección de formaciones, visión artificial, voz, más de dos idiomas, apuestas o fantasy, datos reales.

---

## 7. La experiencia

*Ejemplos ilustrativos. Clubes ficticios: **Kestrel Athletic** (KES, local) frente a **Harbourside United** (HAR, visitante). Comprobar que no coinciden con clubes reales antes de grabar.*

### 7.1 Previa: "Sealed Plans"
- Los dos cuerpos técnicos trabajan **en paralelo y aislados**. En modo analista se ve el rastro (herramientas llamadas, claims).
- **Informe del analista de KES** (≤ 5 hallazgos con `n`):
  - *"HAR's left-back (#3) loses the ball under pressure at about twice the league rate (n = 41 pressured receptions, 8 matches)."*
  - *"HAR plays 78 % of goal kicks short."*
  - *"HAR concedes first contact at the back post on corners."*
- **Plan A de KES: "Squeeze the left-back"**
  - Palancas: `press_height=high`, `press_target=HAR-3`, `attack_channel=right`, `corner_delivery=far_post`.
  - KPIs: ≥ 6 robos altos al descanso · ≥ 40 % de entradas al último tercio por la derecha · xG a balón parado ≥ 0,30.
  - Plan B: si los robos altos van *failing* en el 30', `press_height=mid`.
  - Valoración: *"+0.21 xPts vs default plan (500 sims, 90 % interval ±0.08)"*.
- **Plan A de HAR: "Go over the press"**: `build_up=direct` si les roban arriba, ataque por el centro.
- **Overlay:** dos tarjetas de plan enfrentadas, cada una con *"Sealed 14:58 · sha256 3f9a…"*.

### 7.2 Directo: "Plan Tracker"
- 18': *"KES · Squeeze the left-back ✅ on track · 4 high turnovers (target 6 by HT)"*.
- 27': el **Plan B de HAR** se dispara (le han robado arriba 3 veces) y pasa a salir en largo. El motor detecta la adaptación **con eventos**: los saques de puerta largos pasan del 22 % al 71 %.
- 31': *"⚠️ At risk: HAR stopped playing short. High turnovers stuck at 4."*
- 39': gol de HAR tras un balón a la espalda.
- En modo analista: cada KPI con su `n`, el valor esperado a esta altura y el enlace a sus eventos.

### 7.3 Descanso: "The Duel"
KES pierde 0-1. **Los dos cuerpos técnicos trabajan a la vez, aislados.** En pantalla se ven las dos salas en paralelo.

**1. Cada banquillo formula sus 3 opciones** (la primera siempre es *Stay the course*), revisadas por su analista con evidencia (*"Option C relies on high turnovers, but their long-ball share is 71 % since 27'"*):

| KES | HAR |
|---|---|
| A. *Stay the course* (presión alta) | X. *Stay the course* (seguir en largo) |
| B. Bloque medio + córners al segundo palo | Y. Volver a salir en corto |
| C. Doble cambio ofensivo (dos extremos) | Z. Bloque bajo para proteger el 1-0 |

**2. Cada analista estima qué hará el rival** (sin ver sus opciones reales; infiere 3 opciones probables y sus probabilidades a partir de claims: marcador, arquetipo, adaptación observada, hábitos del historial):
- Analista de KES: *"HAR: stay long 50 % · back to short 15 % · low block 35 %"*.

**3. Cada míster decide con su matriz creída** (sus opciones × las opciones estimadas del rival, 300 réplicas por celda) y elige con una regla explícita: *safe pick* o *gamble*, según el marcador y su perfil.

**4. Las dos elecciones se sellan** (hash) y se revelan a la vez: **KES elige B (safe pick); HAR elige Z (bloque bajo)**.

**5. La retransmisión enseña la matriz real** (opciones reales × opciones reales, 500 réplicas con las mismas semillas, ΔxPts de KES frente a *Stay / Stay*):

|  | **X. HAR sigue en largo** | **Y. HAR vuelve al corto** | **Z. HAR bloque bajo** | Peor caso |
|---|---|---|---|---|
| **A. KES sigue presionando** | 0,00 | **+0,12** | −0,03 | −0,03 |
| **B. Bloque medio + segundo palo** | **+0,14** | +0,04 | +0,05 ◀ elegidas | **+0,04 → safe pick** |
| **C. Doble cambio ofensivo** | −0,04 | +0,08 | **+0,10** | −0,04 |

- **En negrita, la mejor respuesta de KES a cada opción de HAR.**
- **Lectura para el aficionado** (texto con marcadores, rellenado desde claims): *"KES's best move depends on HAR. If HAR keep going long, the mid-block wins. If they go back to short, keep pressing. If they sit deep, go for the double change. The mid-block is the safe pick: it never loses value."*
- **En modo analista:** intervalo de cada celda, `n`, la matriz creída de cada banquillo junto a la real y la diferencia entre "lo que creía el banquillo" y "la realidad".
- **Recuperación de fallos visible:** el míster de KES propone un cambio con un jugador ya sustituido → el validador lo rechaza con el motivo → el míster lo rehace.

### 7.4 Final: "Whose plan won?"
- **2-1 para KES** (remate al segundo palo en el 58' y gol en el 84').
- **Balance de planes:** cada KPI ✅/⚠️/❌. El Plan A de KES fracasó cuando HAR se adaptó; el ajuste del descanso funcionó.
- **Arrepentimiento de cada banquillo** (sobre la matriz real, no sobre una réplica):
  - KES: *"KES's safe pick left 0.05 xPts on the table: HAR parked the bus, and the double attacking sub was the answer."* (mejor respuesta a Z = C, +0,10, frente a B, +0,05).
  - HAR: *"HAR read it right: against the mid-block, sitting deep cost them almost nothing."* (arrepentimiento ≈ 0,01 en sus xPts).
- **La opción no elegida:** la C, jugada con las mismas semillas, en esta réplica acaba 2-1 igual. *"One replay is an anecdote; the distribution is the evidence."*
- Crónica verificada en EN/ES, para aficionado o analista.

*Los valores de la matriz son ilustrativos y coherentes entre sí; los reales saldrán del simulador.*

### 7.5 Personalización
- **Aficionado:** frases cortas, números redondos, ✅/⚠️/❌, sin intervalos.
- **Analista:** `n`, intervalos, distribución de las réplicas, rastro de agentes y evidencias.
- **Club favorito:** primero ves tu cuerpo técnico y tu plan, y los ΔxPts desde tu lado.
- **Idioma:** EN/ES (coma decimal en ES).

---

## 8. Arquitectura

```
                          CONTRATOS (día 0)
 ┌───────────────────────────┐  events · snapshots  ┌───────────────────────────────────┐
 │ SIMULADOR (vectorizado)   │ ───────────────────▶ │ MOTOR (agnóstico al proveedor)    │
 │ zonas · 5 palancas ·      │                      │ · scouting (tendencias + n)       │
 │ fatiga · córners · Plan B │ ◀── fork(state, Δ) ─ │ · KPIs / Plan Tracker / adaptación│
 │ R réplicas en paralelo    │                      │ · valoración ΔxPts · xG propio    │
 │ + capa visual (demo)      │                      │ · claims store                    │
 └───────────┬───────────────┘                      └────────────────┬──────────────────┘
             │ truth + sim_config (solo evaluador)                   │
             ▼                                                       ▼
 ┌───────────────────────────┐              ┌──────────────────────────────────────────┐
 │ EVALUADOR E1–E4           │              │ SERVIDOR MCP (Container Apps)            │
 └───────────────────────────┘              │ ~10 herramientas · ámbito por equipo     │
                                            └──────┬──────────────────────────┬────────┘
                                                   │ MCP (scope KES)          │ MCP (scope HAR)
                              ┌────────────────────▼─────┐   muro   ┌─────────▼────────────────┐
                              │ KES: ANALISTA → MÍSTER   │  ✕✕✕✕✕  │ HAR: ANALISTA → MÍSTER   │
                              └────────────┬─────────────┘          └─────────┬────────────────┘
                                           │ plan sellado (hash)              │
                                           ▼                                  ▼
                              ┌───────────────────────────────────────────────────────────┐
                              │ REGISTRO DEL PARTIDO (planes, hashes, KPIs, decisiones)   │
                              └────────────────────────────┬──────────────────────────────┘
                                                           ▼
                              ┌───────────────────────────────────────────────────────────┐
                              │ REALIZADOR → VERIFICADOR (código) → LOCALIZADOR → CUES    │
                              │ CRONISTA (final)                                          │
                              └────────────────────────────┬──────────────────────────────┘
                                                           ▼
                              ┌───────────────────────────────────────────────────────────┐
                              │ FRONTEND React (Static Web Apps) · match_bundle.json      │
                              │ retransmisión · escritorio de analista                    │
                              └───────────────────────────────────────────────────────────┘
         Agentes: Microsoft Agent Framework + modelos en Foundry · trazas OpenTelemetry → App Insights
```

**Reglas de arquitectura (cada una con su test):**
1. **El motor y los agentes nunca leen `truth` ni `sim_config`.** El paquete del motor solo importa del simulador la interfaz `simulate()/fork()`, que recibe y devuelve contratos.
2. **Separación de información:** el host de cada agente pone la cabecera `X-Team-Scope`, y el servidor MCP filtra. Ninguna herramienta devuelve el plan del rival, sus rasgos ocultos ni su condición física.
3. **Planes y elecciones sellados:** antes de simular el partido se escribe el SHA-256 del JSON canónico de cada plan en el registro (y en un commit del bundle de la demo). En el descanso se hace lo mismo con la elección de cada banquillo **antes** de simular la segunda parte. Al revelarlos se verifica el hash.
3b. **La matriz real es solo para la retransmisión:** `get_true_matrix` solo está disponible con el ámbito `broadcast` (realizador y cronista) y **después** de que se sellen las dos elecciones. Un test comprueba que un cuerpo técnico no puede llamarla.
4. **El LLM no escribe cifras:** solo marcadores que rellena el código; cada frase cita al menos un claim.
5. **Determinismo:** misma semilla y mismos planes dan el mismo partido; las bifurcaciones usan números aleatorios comunes.
6. **Orden temporal:** el pipeline procesa en orden (preparado para un feed en vivo). La demo usa un bundle precalculado y marcado como tal.

### Correspondencia con las 5 etapas del reto
| Etapa | Componente |
|---|---|
| (a) Ingest | El motor consume eventos y snapshots en orden temporal |
| (b) Interpret | Scouting, KPIs del plan, adaptación del rival, xG, xPts |
| (c) Explain | Agentes con claims: por qué el plan funciona o falla y cuánto vale cada ajuste |
| (d) Render | Cue sheet con marca de tiempo + vista de retransmisión + escritorio de analista |
| (e) Personalize | Aficionado / analista, club favorito, EN/ES |

---

## 9. Componentes en detalle

### 9.1 Contratos de datos
Heredan las convenciones de la v3.1 (105×68 m, origen fijo, dirección por parte en `match_meta`).

- **`events`**: `event_id, match_id, t, period, minute, possession_id, type, team, player_id, zone, x, y, end_x, end_y, receiver_id, outcome, under_pressure, body_part, set_piece_ref`.
  - `type` ∈ `pass | long_ball | cross | carry | shot | goal | pressure | tackle | interception | clearance | foul | corner | goal_kick | throw_in | kick_off | sub | possession_change | recovery`.
  - **El xG lo calcula el motor** (distancia, ángulo, parte del cuerpo, contexto), no el simulador.
- **`snapshot`** (cada minuto y en eventos clave): marcador, minuto, cambios usados, jugadores en el campo, condición física **estimada por el motor** a partir de la carga observable y estado de los KPIs.
- **`squads`**: jugadores ficticios con atributos **visibles** (0–100): posición, ritmo, pase, aguante, resistencia a la presión, juego aéreo, finalización. Cada club ve los suyos; del rival solo ve eventos.
- **`plan`**: palancas, KPIs, Plan B, cambios, evidencias (claims) y sello (Anexo B.1).
- **`claim`**: `claim_id, type (observed_tendency | observed_adaptation | sim_valuation | observed_mechanism), team, player_id?, metric, value, league_ref?, n, interval?, evidence[], status (sufficient | insufficient)`.
- **`cue`**: overlay con marca de tiempo (§9.12).
- **Solo para el evaluador:** `truth` (rasgos ocultos por equipo y jugador) y `sim_config` (semilla, coeficientes y rangos de los arquetipos).

### 9.2 Simulador por zonas, vectorizado sobre réplicas
**Requisito de diseño:** valorar 3 opciones × 500 segundas partes en < 20 s, y toda la temporada en minutos. Un bucle por acción en Python puro (unas 1.500–2.000 acciones por partido) no llega. Por eso:

**Una sola función, R réplicas a la vez:**
- **Estado** en arrays de numpy de tamaño `R`: zona del balón, equipo en posesión, jugador poseedor, minuto, marcador, palancas activas, cambios usados; fatiga en un array `(R, 22)`.
- **Cada paso** avanza **una acción en todas las réplicas a la vez**: logits de acción vectorizados → muestreo → éxito → transición de zona o pérdida → tiro y gol → reloj. Las réplicas terminadas se enmascaran.
- **Números aleatorios comunes:** los uniformes se generan por (réplica, paso, uso) a partir de la semilla de la réplica. Dos opciones bifurcadas desde el mismo estado consumen **los mismos uniformes**, así que la diferencia entre ellas refleja la decisión y no el azar.
- **Registro de eventos solo con `R = 1`** (`log=True`) para el partido de la demo y la temporada. El Monte Carlo no registra eventos y es rápido. **Es la misma función**: no hay dos simuladores que puedan divergir.

**Campo:** 6 franjas a lo largo × 3 carriles = 18 zonas (+ marca de "área"). Las coordenadas `x, y` de los eventos se muestrean dentro de la zona.

**Bucle por acción:**
1. **Acción del poseedor:** pase corto, pase progresivo, balón largo, conducción, centro (carriles exteriores, franjas 5–6) o tiro. Es un softmax cuyos pesos dependen de la zona, de las palancas `build_up` y `attack_channel` y del marcador.
2. **Éxito:**
   `logit p = α[acción, zona] + β_s·(habilidad − 50)/50 − β_p·Presión_rival(zona)·(1 − resistencia_a_la_presión) + β_f·(fatiga_rival − fatiga_propia)`
   - `Presión_rival(zona)` depende de `press_height` del rival (high: franjas 1–3 propias; mid: 3–4; low: 5–6), de **`press_target`** (más presión si recibe el jugador señalado) y de su fatiga.
3. **Fallo:** pérdida en la zona. Si el robo es en campo rival, hay **ventana de contraataque** de 10 s con bonificación de llegada.
4. **Tiro:** probabilidad interna de gol según la zona, el contexto (contraataque, cabezazo tras centro) y la finalización.
5. **Tiempo:** de 2 a 6 s por acción más paradas, para unos 55–60 min de balón en juego.
6. **Plan B:** cada minuto se evalúan los disparadores de ambos planes y se aplican.
7. **Cambios:** 5 en 3 ventanas más el descanso (lo impone el validador).

**Las 5 palancas (§9.3) y su matriz de interacciones** (cada fila con su test en `dev`):

| Si el rival… | …y nosotros… | Efecto esperado |
|---|---|---|
| `press_height=high` | `build_up=short` con jugadores poco resistentes a la presión | Más robos altos para el que presiona |
| `press_height=high` | `build_up=direct` con delantero rápido contra central lento (rasgo oculto) | Más balones a la espalda y uno contra uno |
| Tiene un lateral débil bajo presión (oculto) | `press_target` = ese lateral y `attack_channel` por su lado | Más robos y progresión por ese carril |
| Defiende mal el segundo palo (oculto) | `corner_delivery=far_post` | Más primeros contactos y xG de cabeza |
| `press_height=high` durante 90' | — | Más fatiga → peor presión y más errores en el tramo final |

**Micro-modelo de córner:** `entrega ∈ {near_post, far_post, short}` × `marcaje del rival (zonal | man)` × duelos aéreos × debilidad oculta → P(primer contacto) → P(tiro) → P(gol). Objetivo: unos 10 córners por partido y unos 0,03–0,05 goles por córner.

**Fatiga:** `s_i(t) ∈ [0, 1]`, con desgaste por minuto según el rol y coste extra si `press_height=high` (×1,4). Efectos: eficacia de la presión × (0,6 + 0,4·s) y más errores.

**Bifurcación:** `fork(state, overrides, R, seed) → outcomes(R)`, donde `outcomes` incluye goles por equipo, xPts, trayectorias de los KPIs y fatiga final.

**Rendimiento:** el objetivo es ≥ 500 partidos completos por segundo con `R = 500` en un núcleo. **Se mide el viernes 23 (H1).** Si no se llega, se reduce `R` a 300 y se precalcula todo lo de la demo.

### 9.3 Palancas tácticas
| Palanca | Valores | Efecto principal |
|---|---|---|
| `press_height` | high / mid / low | Zonas de presión, coste de fatiga, espacio a la espalda |
| `press_target` | player_id / none | Presión extra cuando ese jugador recibe |
| `build_up` | short / mixed / direct | Mezcla de pase corto y balón largo desde las franjas 1–2 (incluidos los saques de puerta) |
| `attack_channel` | left / center / right / balanced | Reparto de las acciones de progresión por carril |
| `corner_delivery` | near_post / far_post / short | Micro-modelo de córner |
| `subs_plan` | lista de {ventana, sale, entra} | Validado por reglas |
| `plan_b` | lista de {condición → cambios de palanca o de jugador} | Lo aplica el simulador |

### 9.4 Equipos, jugadores y rasgos ocultos
- **6 clubes ficticios** (4 en `dev`, 2 en `test`) con plantillas de 18 jugadores. Atributos generados por **arquetipo** (presionante, de posesión, directo, de bloque bajo) más ruido.
- **3 rasgos ocultos por equipo**, sacados de un catálogo de 6:

| Rasgo (en `truth`) | Efecto en el simulador | Cómo lo puede descubrir el scouting |
|---|---|---|
| `fb_low_press_resistance(player)` | Penaliza el éxito de ese lateral bajo presión | Pérdidas bajo presión por cada 100 recepciones frente a la media de su posición |
| `cb_low_pace(player)` | Más éxito de los balones a la espalda en su zona | Balones a la espalda concedidos por zona |
| `back_post_weak` | Menor P(primer contacto defensivo) en el segundo palo | Primer contacto concedido según la zona de entrega |
| `gk_short_bias` | Saques de puerta en corto ≥ 75 % aunque le presionen | % de saques de puerta en corto, con y sin presión rival |
| `late_fade` | Más desgaste por minuto | xG concedido del 75' al 90' frente al resto del partido |
| `weak_channel(side)` | Peor defensa en ese carril | Entradas y centros concedidos por carril |

- Los equipos `test` tienen otros arquetipos y combinaciones de rasgos.

### 9.5 Temporada sintética (dataset)
- **8 partidos por equipo** (liga a doble vuelta parcial), con planes por defecto según el arquetipo y algo de variación.
- Se exporta en el contrato `events`. Es el material del analista y la aportación de *data innovation*.
- La tabla de calibración se calcula sobre la temporada (Anexo A).

### 9.6 Scouting: 4 funciones deterministas
Cada una devuelve claims con `n`, la comparación con la liga y `insufficient` si `n` < umbral:
1. **Salida de balón:** % de saques de puerta en corto y tasa de balón largo, con y sin presión rival.
2. **Pérdidas bajo presión por jugador**, por cada 100 recepciones presionadas, frente a la media de su posición.
3. **Defensa por carril:** entradas al último tercio, centros y balones a la espalda concedidos por carril y por zona.
4. **Defensa de córners:** primer contacto concedido según la zona de entrega y xG concedido a balón parado.

Además, `fade_profile(team)`: xG concedido del 75' al 90' frente a su media (para `late_fade`).

### 9.7 Plan Tracker y adaptación
- **KPIs:** `high_turnovers`, `final_third_entries_share(channel)`, `set_piece_xg`, `balls_in_behind_conceded`.
- **Estado:** `on_track / at_risk / failing / insufficient_evidence`. Se compara lo observado con la **trayectoria esperada** de ese KPI según las simulaciones de la previa (media y banda), no con una regla de tres. Con histéresis y siempre con `n`.
- **Una detección de adaptación:** cambio de régimen en el % de saques de puerta y balones largos (ventana móvil + umbral). Genera un claim `observed_adaptation` con su ventana y su `n`.
- **Disparadores de cue:** cambio de estado de un KPI, gol, adaptación detectada, Plan B activado, descanso y final.

### 9.8 Capa visual del campo 2D (solo la demo)
- El partido de la demo se dibuja con las **formas ancladas al balón** de la v3.1: las posiciones se derivan de la zona del balón, de la fase y de las palancas activas (bloque más alto con `press_height=high`), con ruido continuo.
- Se mantienen los invariantes visuales: la posición del evento coincide con la del balón y el receptor está al final del pase.
- **Se presenta como visualización, no como tracking analizado.** No se calcula ninguna métrica a partir de estas posiciones.

### 9.9 Valoración: puntos esperados y el duelo
**xPts** de un equipo sobre R réplicas = 3·P(victoria) + 1·P(empate).

**Previa:** `simulate_plan(plan, opponent_plan_estimate, R=500)` devuelve victoria / empate / derrota, xPts, xG a favor y en contra y trayectorias de los KPIs.

**Descanso, el duelo:**
- **Opciones:** cada banquillo tiene 3 (`O_KES`, `O_HAR`), y la primera siempre es *Stay the course*. Una opción es un conjunto de cambios de palanca y/o de jugador, validado.
- **Matriz de pagos:** `M[i, j]` = resultado de jugar la segunda parte con la opción `i` de KES y la `j` de HAR, bifurcando desde el snapshot del descanso. **Todas las celdas usan las mismas semillas** (números aleatorios comunes), así que las diferencias entre celdas reflejan las decisiones y no el azar.
- Cada celda guarda los xPts de los dos equipos y su intervalo. Se presenta como **ΔxPts frente a la celda *Stay / Stay*** desde la perspectiva de cada equipo (el juego no es de suma cero, porque un empate da 1 punto a cada uno).
- **Tres matrices por descanso:**
  1. **Creída por KES:** `O_KES × Ô_HAR` (opciones del rival que estima su analista).
  2. **Creída por HAR:** `O_HAR × Ô_KES`.
  3. **Real (retransmisión):** `O_KES × O_HAR`.

  Son 27 celdas × 300–500 réplicas de una segunda parte. Con el simulador vectorizado, se calculan en segundos y se precalculan para la demo.
- **Lectura de una matriz** (en código, para cada equipo):
  - **Mejor respuesta** a cada opción del rival: la fila con más xPts en esa columna.
  - **Safe pick:** la opción con el mejor peor caso (*maximin* sobre las columnas).
  - **Best guess:** la opción con más xPts esperados según las probabilidades que estima el analista.
  - **Gamble:** la opción, distinta de la *safe pick*, con el mejor caso más alto. Se etiqueta así si su peor caso es claramente peor que el de la *safe pick*.
  - **Dominante:** si una opción es la mejor respuesta en todas las columnas, se anuncia como tal (*"KES has a dominant move"*).
- **Etiquetas de diferencia** entre dos celdas: *Clear gain* (|Δ| ≥ 0,10 y el intervalo no cruza 0), *Marginal* (el intervalo apenas cruza 0) y *Within noise* (el resto).
- **Arrepentimiento** (final del partido, sobre la matriz real): `regret_KES = max_i M[i, j*] − M[i*, j*]`, donde `i*` y `j*` son las elecciones reales. Se calcula sobre la **distribución** de réplicas, no sobre el resultado de la réplica emitida.

**Coherencia con la información privada:** cada cuerpo técnico decide **solo con su matriz creída**. La matriz real solo existe para la retransmisión y se calcula después de sellar las dos elecciones.

**Anticipación (lo que estima el analista):** `estimate_opponent_options(team)` es una función determinista que propone las 3 opciones más probables del rival y sus probabilidades. Se basa en reglas simples sobre claims: marcador (quien gana tiende a protegerse), arquetipo del rival, adaptaciones ya observadas y hábitos del historial (p. ej. cambios tempranos cuando pierde). El analista (LLM) puede **ajustar** las probabilidades citando claims, dentro de límites que impone el validador.

### 9.10 Agentes (Microsoft Agent Framework + modelos en Foundry)

**Por qué hacen falta varios:**
1. **Información privada:** un único agente con todo el contexto vería los dos planes y las dos opciones del descanso: no habría duelo ni anticipación posibles.
2. **Agentes adversarios que se modelan entre sí:** cada analista estima qué hará el otro banquillo, y cada míster decide contra esa estimación sin conocer la elección real.
3. **Herramientas distintas por rol:** el analista solo tiene scouting y anticipación; el míster, simulación, validación, condición física y balón parado.
4. **Bucle de revisión:** el analista puede cuestionar con evidencia una opción del míster.

| Agente | Instancias | Herramientas MCP | Salida |
|---|---|---|---|
| **Analista** | KES, HAR | `list_matches`, `get_team_tendencies`, `get_player_profile`, `get_set_piece_profile`, `estimate_opponent_options` | `ScoutingReport` (≤ 5 hallazgos con claims) + `OpponentPlanEstimate`; en el descanso, `OpponentOptionsEstimate` (3 opciones + probabilidades + claims) |
| **Míster** | KES, HAR | `get_squad_condition`, `simulate_plan`, `price_matrix`, `validate_plan`, `get_plan_status` | `GamePlan` sellado; en el descanso, 3 opciones, **elección sellada** con su regla (*safe pick / best guess / gamble*) y 3 mensajes de charla |
| **Realizador** | 1 | `get_match_state`, `get_plan_status`, `get_events`, `get_true_matrix` (ámbito `broadcast`) | Qué cue sale (prioridad, duración, sin solapes) + texto con marcadores |
| **Cronista** | 1 | Lectura (todas, ámbito `broadcast`) | "Whose plan won?" con claims y el arrepentimiento de cada banquillo |
| **Localizador** | 1 | — | EN/ES × aficionado/analista, conservando los marcadores |

**En código, no en LLM:** simulador, motor de KPIs, scouting, valoración, validador de planes, verificador de textos y sellado.

**Modelos:** uno mayor para el míster y el realizador y uno pequeño para el resto. **El día 0 hay que confirmar** la cuota y los modelos disponibles en la suscripción, y prever un modelo de respaldo. Las recomendaciones de la v4 sobre qué modelos se retiran no las hemos verificado.

### 9.11 Workflows
**WF-Previa** (por equipo, los dos en paralelo y aislados):
1. **Analista** → `ScoutingReport` + `OpponentPlanEstimate`.
2. **Traspaso al míster:** propone 2–3 planes candidatos (JSON con esquema), cada palanca no por defecto **cita un claim** → `simulate_plan` contra la estimación → elige uno.
3. `validate_plan`: si falla, el míster revisa (máximo 2 veces); si sigue fallando, se usa una plantilla del arquetipo.
4. **Sellado:** el hash va al registro del partido **antes** de simular.

**WF-Directo** (bucle determinista; el LLM solo actúa en los disparadores):
simulador → motor (KPIs, adaptación, xG) → disparadores → **realizador** (con límite de llamadas) → verificador → localizador → cue sheet. El Plan B lo ejecuta el **simulador** (el plan es un contrato) y el overlay lo cuenta.

**WF-Duelo** (descanso; los dos equipos **en paralelo y aislados**, con una barrera de sincronización al final):
1. El analista resume la primera parte con claims.
2. El míster formula 3 opciones (la primera, *Stay the course*) → `validate_plan`.
3. **El analista revisa:** puede marcar una opción como "contradice la evidencia" citando un claim. Solo una ronda.
4. **El analista estima al rival:** `estimate_opponent_options` → `OpponentOptionsEstimate` (puede ajustar las probabilidades citando claims).
5. **El míster valora:** `price_matrix(own_options, estimated_opponent_options)` → su matriz creída con la lectura (mejor respuesta, *safe pick*, *best guess*, *gamble*).
6. **El míster elige** y declara la regla con la que elige, con un texto con marcadores. La elección se **sella**.
7. **Barrera:** cuando los dos equipos han sellado → revelación → el motor calcula la **matriz real** → el realizador emite los cues del duelo → la segunda parte se simula con las dos elecciones.
8. (Opcional) voto de fans antes de la revelación.

**WF-Final:** cronista → verificador → localizador → cues de la crónica, del arrepentimiento de cada banquillo y de la opción no elegida.

**Patrones de Agent Framework:** concurrente (los dos equipos), secuencial con traspaso (analista → míster), bucle de revisión, **barrera de sincronización** (el duelo) y reintentos con validador. **Hay que confirmar el día 0** las versiones de los paquetes y la API de workflows.

### 9.12 Recuperación de fallos
| Fallo | Respuesta | Dónde se ve |
|---|---|---|
| Plan o cambio inválido (6 cambios, jugador ya sustituido, KPI no medible) | Rechazo con motivo → el míster rehace (máximo 2) → plantilla | Rastro: *rejected → revised* |
| Texto con cifras no permitidas o sin claim | Se regenera → plantilla fija | Contador en el panel de validación |
| El modelo no responde | Modelo de respaldo → plantilla | Rastro |
| La simulación tarda demasiado | Reintento con `R` menor → etiqueta *low confidence* | Etiqueta en la tarjeta |

En el vídeo se enseña uno (unos 5 s).

### 9.13 Servidor MCP (Python, HTTP en streaming, Azure Container Apps)
| Grupo | Herramienta | Devuelve |
|---|---|---|
| Scouting | `list_matches(team)` | Partidos del historial |
| | `get_team_tendencies(team, aspect)` | Claims de tendencia con `n` y media de la liga |
| | `get_player_profile(player_id)` | Claims observados (nunca rasgos ocultos) |
| | `get_set_piece_profile(team)` | Claims de balón parado |
| Propios | `get_squad_condition(team)` | Atributos visibles y carga estimada (**solo del propio equipo**) |
| Simulación | `simulate_plan(plan, opponent_estimate, R)` | Claims `sim_valuation` |
| | `price_matrix(match_id, team, own_options[], opponent_options[], R)` | Matriz creída 3 × 3 (claims `sim_matrix_cell`) + lectura: mejor respuesta, *safe pick*, *best guess*, *gamble*, dominante |
| | `estimate_opponent_options(match_id, team)` | 3 opciones probables del rival + probabilidades + claims (**nunca** sus opciones reales) |
| | `seal_choice(match_id, team, option_id)` | Hash de la elección |
| Retransmisión (ámbito `broadcast`) | `get_true_matrix(match_id)` | Matriz real + arrepentimiento; solo **después** de sellar las dos elecciones |
| | `validate_plan(plan)` | OK o lista de errores |
| Directo | `get_match_state(match_id, minute)` | Snapshot |
| | `get_plan_status(match_id, team, minute)` | Estado de los KPIs (**solo del propio equipo** para los cuerpos técnicos) |
| Evidencia | `get_events(match_id, filter)`, `get_claim(claim_id)` | Eventos y claims |

- **Ámbito:** `X-Team-Scope` (`KES`, `HAR` o `broadcast`) la pone el host, no el LLM. **Tests:** con el ámbito KES no se puede leer nada privado de HAR (ni sus opciones del descanso ni su elección antes de la revelación), y ningún cuerpo técnico puede llamar a `get_true_matrix`.
- **Reutilizable desde GitHub Copilot** en modo agente (se documenta en el README).

### 9.14 Validadores
- **De planes:** esquema, valores permitidos, jugadores disponibles, regla de 5 cambios en 3 ventanas + descanso, KPIs de la biblioteca con objetivo medible, disparadores bien formados y **cada palanca no por defecto con al menos un claim**.
- **De textos:** cada cifra procede de un marcador; cada frase cita al menos un claim; verbos causales solo con un claim de mecanismo; idioma correcto; en modo aficionado sin intervalos ni decimales.

### 9.15 Frontend (React + TypeScript + Vite, Static Web Apps)
- **`/` Retransmisión 16:9:** campo 2D, marcador, previa con las dos tarjetas selladas, Plan Tracker en el tercio inferior, alertas, **duelo del descanso** (las dos salas en paralelo → sellos → revelación → `DuelMatrix`), final con el balance de planes, el arrepentimiento de cada banquillo y la opción no elegida.
- **`DuelMatrix`, diseñada para leerse en 15 s:**
  - 3 × 3 desde la perspectiva del **club favorito** (filas: sus opciones).
  - Color por ΔxPts (escala divergente centrada en *Stay / Stay*) y la mejor respuesta de cada columna resaltada.
  - Dos marcadores para las elecciones reales, que se cruzan en una celda.
  - Etiquetas *SAFE* y *GAMBLE* en las filas.
  - **Una frase** de lectura para el aficionado debajo de la matriz.
  - En modo analista: intervalos por celda y un interruptor "matriz creída / real".
- **`/analyst` Escritorio de analista:** los dos planes y sus evidencias, informe de scouting, KPIs con `n`, distribución de las réplicas, **rastro de agentes** (herramientas, parámetros, claims, duración, rechazos y reintentos) y **panel de validación** (E1, E2, E4, un caso de "evidencia insuficiente").
- **Componentes:** `Pitch2D`, `Scorebug`, `PlanCard`, `SealBadge`, `PlanTrackerLT`, `AlertCue`, `DuelRooms` (las dos salas en paralelo), `DuelMatrix`, `RegretCard`, `PlanScorecard`, `AgentTrace`, `ValidationPanel`, `Settings`.
- **Datos:** `match_bundle.json` precalculado (eventos, snapshots, posiciones de la capa visual, planes y hashes, cues, trazas, evaluaciones). **La demo funciona sin backend.**

### 9.16 Cue sheet
```json
{"cue_id": "q-031-kes-risk", "t_match": "31:04", "template": "plan_alert",
 "priority": 2, "ttl_s": 12, "team": "KES",
 "fields": {"plan": "Squeeze the left-back", "kpi": "high_turnovers",
            "status": "at_risk", "value": "{c112.value}", "target": "{c112.target}"},
 "text": {"en": "...", "es": "..."}, "mode": ["casual", "analyst"],
 "claims": ["c112", "c113"]}
```
**Plantillas:** `plan_card`, `plan_sealed`, `plan_tracker_lt`, `plan_alert`, `adaptation_detected`, `plan_b_fired`, `duel_rooms`, `duel_sealed`, `duel_reveal`, `duel_matrix`, `plan_scorecard`, `bench_regret`, `option_not_taken`. Se exporta en JSON.

---

## 10. Stack y despliegue

| Capa | Tecnología |
|---|---|
| Código | GitHub (repo **público**) + GitHub Copilot en modo agente (uso documentado en `docs/COPILOT_USAGE.md`) |
| Simulador, motor, evaluador | Python 3.12 (numpy, pandas, pydantic) + pytest |
| Herramientas | **Servidor MCP** (SDK MCP de Python, HTTP en streaming) en **Azure Container Apps** |
| Agentes | **Microsoft Agent Framework** (Python) + modelos en **Microsoft Foundry**. Los workflows se ejecutan offline para generar el bundle y, en vivo, desde el mismo contenedor si da tiempo |
| Observabilidad | OpenTelemetry → **Application Insights** conectado al proyecto de Foundry; spans con `claim_id` y `cue_id` |
| Frontend | React + TypeScript + Vite en **Azure Static Web Apps** |
| CI | GitHub Actions: pytest (invariantes, contratos, separación de información, sellado, determinismo) |
| Coste y disponibilidad | Alerta de presupuesto · réplica mínima 1 en Container Apps **hasta el 10 nov** · modo estático sin backend |

**Día 0 de Azure (máximo 2 h):** proyecto de Foundry, despliegue de los 2 modelos, **comprobación de cuota**, App Insights, grupo de recursos con Container Apps y Static Web Apps. Despliegue con la CLI (`az`) o `azd` sin Bicep a medida.

---

## 11. Evaluación

| ID | Qué medimos | Cómo | Dónde se ve |
|---|---|---|---|
| **E1** | **Scouting frente a la verdad oculta** (titular) | Rasgos señalados por el analista en los equipos `test` frente a `truth` → precisión y recall | Panel de validación + vídeo |
| **E2** | Estabilidad de la valoración | ΔxPts con R = 300 frente a R = 3.000 en N puntos de decisión → acierto de signo, error medio, cobertura del intervalo. *Mide el ruido del Monte Carlo, no la validez del modelo* | Panel de validación |
| **E3** | Decisiones coherentes con la evidencia | % de palancas no por defecto que citan un claim válido; % de planes que atacan al menos un rasgo oculto real | Panel de validación |
| **E4** | Narración fundamentada | % válido a la primera, % tras reintento, 0 cifras del LLM | Panel de validación |
| **E7** | **Anticipación del rival** | En N descansos de `test`: probabilidad media que el analista asignó a la opción que el rival eligió de verdad (y *log loss*), frente al reparto uniforme | Panel de validación |
| **E8** | **Arrepentimiento frente a referencias** | En N descansos de `test`: arrepentimiento medio del míster IA frente a "no tocar nada siempre" y "elegir al azar", con intervalo. *Mide decisiones dentro de nuestro simulador* | Panel de validación + vídeo |
| E5 (opcional) | Evaluaciones de Foundry | Evaluadores de agente sobre 20–30 casos | README |
| E6 | Realismo | Tabla de calibración + invariantes | README |

Los umbrales se fijan con `dev` y se congelan antes de evaluar en `test`.

**Transparencia sobre la circularidad.** Los rasgos ocultos y la matriz de interacciones son nuestros. Lo mismo vale para la matriz del duelo: sus valores salen de nuestras reglas. Lo que no es circular es que **cada banquillo decide sin ver al otro** y que medimos cuánto acierta anticipándolo (E7). Por eso:
- **E1** mide si los agentes **descubren** algo que no ven, a partir de eventos con ruido. Esa parte no es circular.
- **ΔxPts** mide el valor de una decisión **dentro de nuestro modelo**. Se presenta así ("in our simulator"), nunca como una predicción del mundo real.

---

## 12. Estructura del repositorio

```
plan-a/
├── contracts/        # JSON Schemas (events, snapshot, squads, plan, claim, cue) · tools.md (firmas MCP) · sim_api.md (simulate/fork)
├── fixtures/         # partido falso (~300 eventos) + 2 planes + respuestas canned de las herramientas
├── sim/              # simulador vectorizado: zonas, acciones, palancas, fatiga, córners, plan_b, fork, teams, season
│   └── render/       # capa visual de formas ancladas al balón (de v3.1)
├── engine/           # xG propio, scouting, KPIs/tracker, adaptación, valoración ΔxPts, claims store
├── mcp_server/       # herramientas MCP, ámbito por equipo, mock_engine
├── agents/           # Agent Framework: roles, prompts, workflows (previa, directo, descanso, final)
│   └── validators/   # validador de planes y verificador de textos
├── eval/             # E1–E4 (+E5), calibración, datos del panel de validación
├── web/              # React: retransmisión, escritorio de analista, componentes
├── data/             # generado (gitignored salvo match_bundle.json de la demo)
├── tests/            # invariantes, contratos, separación de información, sellado, determinismo, matriz de interacciones
└── docs/             # ARCHITECTURE, METHODS, CALIBRATION, TRANSPARENCY, COPILOT_USAGE, DECISIONS
```

---

## 13. Roadmap (hora peninsular)

**Reparto:**
- **Persona A, "Simulación y motor":** `sim/`, `engine/`, `eval/`.
- **Persona B, "Agentes y producto":** `mcp_server/`, `agents/`, `web/`, despliegue.
- **Compartido:** `contracts/`, `fixtures/`, `tests/`.

| Día | Persona A | Persona B | Hito de la noche |
|---|---|---|---|
| **Jue 22 (tarde)**, día 0 | **Los dos (2–3 h):** contratos + `sim_api.md` + `tools.md` · fixtures · repo y CI · Azure día 0 (cuota de modelos) | | **H0:** contratos en `main`; el fixture se valida contra los esquemas; un modelo responde desde Foundry |
| **Vie 23** | Simulador vectorizado: zonas, acciones, modelo de éxito, tiros, córners, fatiga, cambios, Plan B · invariantes · **medición de rendimiento** | `mock_engine` + servidor MCP (todas las herramientas canned, ámbito por equipo + test) · analista y míster contra el mock · `Pitch2D`, `Scorebug`, `PlanCard` con el fixture | **H1:** 90' simulados desde dos planes con invariantes en verde y rendimiento medido · un míster produce un plan válido contra el mock |
| **Sáb 24** | Equipos + rasgos ocultos · temporada · 4 funciones de scouting · KPIs + adaptación · `simulate_plan` / **`price_matrix`** (con números aleatorios comunes) · `estimate_opponent_options` · lectura de la matriz y arrepentimiento | **13:00 integración:** MCP sobre el motor real · WF-Previa completo (los dos equipos aislados, validación, sellado) · realizador + verificador → cues · `PlanTrackerLT`, `AlertCue` | **H2:** un partido de punta a punta en local: planes → simulación → KPIs → cues → UI |
| **Dom 25** (el reloj se atrasa 1 h a las 03:00) | E1–E3, **E7 y E8** sobre `dev` y congelar umbrales · tabla de calibración · test de la matriz de interacciones · búsqueda de semilla para la historia de la demo (documentada) · capa visual | **WF-Duelo** (los dos equipos en paralelo, sellado, barrera, revelación) · **`DuelMatrix`**, `DuelRooms`, `RegretCard`, final · **despliegue en Azure** · fallo con recuperación visible | **H3:** URL pública de punta a punta con el duelo · **decisión de categoría** |
| **Lun 26** | Evaluación en `test` · datos del panel de validación · README (métodos, calibración, transparencia) | Cronista + localizador · `/analyst` con `AgentTrace` y `ValidationPanel` · exportar la cue sheet · pulido de UX | **H4 (22:00): congelación de funcionalidades** · ensayo del guion |
| **Mar 27** | Solo bugs · grabación · pitch y texto de entrega · instrucciones de prueba | Solo bugs · montaje del vídeo (< 2 min) y subida · verificar el despliegue · repo público | **Enviar antes de las 20:00** |

**Recortes si un hito falla (sin perder la demo):**
- **H1 falla:** se quita `corner_delivery` y la fatiga pasa a ser lineal y fija; `R = 300`.
- **H2 falla:** el realizador pasa a plantillas sin LLM; el míster recibe el informe del analista como texto precalculado.
- **H3 falla:** el duelo baja a **2 × 2** (*Stay* + una alternativa por banquillo) y sin revisión del analista; la estimación del rival se queda en la función determinista, sin ajuste del LLM. Si ni eso llega, se vuelve a la valoración de un solo banquillo de la v5. La demo se sirve estática.
- **H4 falla:** solo EN y crónica sencilla.

**Reglas de paralelización:**
1. **Contratos y mock primero:** B no depende de A hasta el sábado a las 13:00 (se cambia una variable de entorno).
2. **Rebanadas verticales:** cada noche hay algo que funciona de punta a punta, aunque sea feo.
3. **Propiedad por carpetas;** `contracts/` lo revisan los dos.
4. **PRs pequeños** (menos de un día) con la CI en verde.
5. **Sincronizaciones** a las 10:00 y a las 22:00; decisiones en `docs/DECISIONS.md`.
6. **Regla de no bloqueo:** si falta algo del otro, se usa el fixture.

**Ruta crítica:** `contracts → sim vectorizado → fork / price_matrix → WF-Duelo → DuelMatrix → vídeo`. **Mitigación:** `price_matrix`, `estimate_opponent_options` y `get_true_matrix` existen en el mock desde el viernes, con una matriz de ejemplo coherente (la de §7.3).

---

## 14. Guion del vídeo (< 2 min, objetivo unos 110 s)

| Tiempo | Contenido |
|---|---|
| 0–12 s | **Gancho:** *"Every manager has a Plan A. The other manager has an answer."* Las dos tarjetas de plan aparecen **selladas** (hash) |
| 12–40 s | **Previa:** los dos cuerpos técnicos trabajan aislados (rastro de agentes). El analista de KES encuentra al lateral débil (`n = 41`) → el míster construye "Squeeze the left-back", +0,21 xPts → se sella |
| 40–62 s | **Directo:** ✅ on track → HAR se adapta (saques largos del 22 % al 71 %, detectado con eventos) → ⚠️ at risk → gol de HAR |
| 62–90 s | **El duelo:** las dos salas en paralelo → cada analista estima al rival → **fallo y recuperación** (cambio inválido rechazado → rehecho) → dos sellos → revelación → **`DuelMatrix`**: *"If HAR keep going long, the mid-block wins…"* · KES = *safe pick*, HAR = bloque bajo |
| 90–100 s | **Final:** remate al segundo palo, 2-1 · balance de planes · **arrepentimiento**: *"KES's safe pick left 0.05 xPts on the table"* |
| 100–112 s | **Bajo el capó:** **E1** (el scouting encontró X de Y rasgos ocultos en equipos que nunca vio), **E7/E8** (cuánto anticipa cada analista y cuánto menos se arrepiente el míster IA que las referencias), trazas, servidor MCP usado desde Copilot, arquitectura en Azure, *"synthetic data, fictional clubs, values inside our simulator"* |

Sin logos, marcas ni música de terceros. 1080p, con voz propia si se puede. Cronometrar antes de grabar.

---

## 15. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Parecer una copia de *The Dugout* | El centro es el **duelo contra la respuesta del rival**, la previa, el scouting medido y los sellos; ΔxPts y etiquetas propias; sin gancho NFL / F1; el voto, opcional; frase explícita en el pitch |
| La matriz 3 × 3 no se entiende en pantalla | `DuelMatrix` desde el club favorito, color + dos marcadores + *SAFE* / *GAMBLE* + **una** frase; probarla con alguien que no conozca el proyecto antes de grabar; versión 2 × 2 como respaldo |
| El duelo no da historias interesantes (una opción domina siempre) | Test en `dev`: en al menos la mitad de los descansos, la mejor respuesta tiene que depender de la opción del rival; si no, se ajustan las interacciones entre palancas. Si una opción domina, se anuncia (*"dominant move"*) |
| El LLM manipula la estimación del rival | La estimación base es determinista; el ajuste del analista está acotado por el validador y tiene que citar claims |
| Fuga de información entre banquillos en el descanso | Ámbito por equipo, `get_true_matrix` solo con `broadcast` y después de los sellos, tests de separación |
| El simulador vectorizado se complica | Una sola función con `R` y `log`; rendimiento medido en H1; recortes de H1 |
| Las palancas no se notan en el resultado | Tests de la matriz de interacciones en `dev`; ajustar coeficientes |
| Las palancas dominan demasiado | Calibración + límites: el ΔxPts de una táctica tiene que ser de décimas, no de puntos |
| "Habéis puesto vosotros los patrones" | E1 mide el descubrimiento con eventos con ruido en equipos `test`; transparencia explícita (§11) |
| El LLM propone tácticas sin sentido | Planes con esquema, cada palanca con un claim, validador, valoración por simulación, plantilla de respaldo |
| Cuota o modelo no disponible | Comprobarlo el día 0; modelo de respaldo; plantillas |
| La API de Agent Framework cambia | Fijar versiones el día 0; los workflows, simples (secuencial + concurrente + bucle) |
| Fallo durante la grabación | Bundle precalculado marcado como tal |
| Demo caída antes del 10 nov | Réplica mínima 1, alerta de presupuesto, modo estático |
| Lectura de apuestas | Sin cuotas ni mercados; xPts como herramienta de explicación |
| Nombres de clubes reales | Comprobarlos antes de grabar |

---

## 16. Definición de "terminado"

- [ ] URL pública en Azure; la demo funciona sin login y sin backend si algo cae.
- [ ] Simulador vectorizado determinista con 5 palancas, fatiga, córners, cambios y Plan B; invariantes y matriz de interacciones en verde; rendimiento medido y documentado.
- [ ] 6 clubes con rasgos ocultos y temporada sintética; `dev`/`test`; el motor y los agentes no leen la verdad (test).
- [ ] Separación de información entre cuerpos técnicos (test) y planes sellados con hash verificable, publicado antes de simular.
- [ ] Previa: analista + míster por equipo, planes válidos, valorados (ΔxPts) y sellados, con cada palanca justificada por un claim.
- [ ] Directo: Plan Tracker con estados, adaptación detectada con eventos y cues.
- [ ] Duelo del descanso: los dos banquillos en paralelo y aislados, 3 opciones cada uno, estimación del rival, matriz creída, elección sellada con su regla, revelación y **matriz real 3 × 3** en `DuelMatrix`.
- [ ] Ningún cuerpo técnico puede ver las opciones o la elección del otro ni la matriz real antes de la revelación (tests).
- [ ] Final: balance de planes, **arrepentimiento de cada banquillo**, crónica verificada y opción no elegida.
- [ ] Al menos un fallo con recuperación visible en el rastro y en el vídeo.
- [ ] Ninguna cifra escrita por el LLM; ninguna causa sin claim de mecanismo.
- [ ] Panel de validación con E1, E2, E3, E4, **E7 y E8** y un caso de "evidencia insuficiente".
- [ ] Tabla de calibración en el README con fuentes **revisadas**.
- [ ] Trazas de los agentes visibles (App Insights / Foundry).
- [ ] Aficionado / analista, EN/ES, club favorito.
- [ ] Cue sheet exportable.
- [ ] README: arquitectura, contratos, cómo ejecutarlo, transparencia (§11) y uso de Copilot.
- [ ] Vídeo < 2 min, público en YouTube o Vimeo, sin marcas ni música de terceros.
- [ ] Repo público; todo el material en inglés; pitch (qué hemos construido, tecnologías de Microsoft, qué hace, qué problema resuelve).
- [ ] Categoría declarada.
- [ ] Demo accesible gratis hasta el 10 nov, con instrucciones de prueba.
- [ ] Sin código de otros participantes; dependencias con licencia compatible.

---

## Anexo A. Tabla de calibración (objetivos)

Se reutilizan los objetivos del Anexo A de la v4, **reducidos a 10 métricas medibles con este simulador**. Todas las cifras y fuentes hay que **revisarlas** antes de publicarlas en el README (vienen de una investigación web previa que no hemos verificado).

| Métrica (por partido) | Objetivo aproximado |
|---|---|
| Goles | 2,7–3,0 |
| Victoria local / empate / visitante | ~41 / 25 / 35 % (sobre la temporada) |
| Tiros | ~24–27 |
| Conversión del tiro | ~10–12 % |
| Pases | ~850–900 |
| Acierto en el pase | ~80–85 % |
| Duración media de la posesión | ~9–11 s |
| Robos altos | ~10–14 |
| Córners | ~9–11 |
| % de goles a balón parado (sin penaltis) | ~20–27 % |

## Anexo B. Ejemplos

### B.1 Plan
```json
{
  "plan_id": "KES-A", "team": "KES", "opponent": "HAR",
  "name": {"en": "Squeeze the left-back", "es": "Asfixiar a su lateral izquierdo"},
  "levers": {"press_height": "high", "press_target": "HAR-3", "build_up": "mixed",
             "attack_channel": "right", "corner_delivery": "far_post"},
  "lever_evidence": {"press_target": ["c_sc_03"], "attack_channel": ["c_sc_05"],
                     "corner_delivery": ["c_sp_02"], "press_height": ["c_sc_01"]},
  "kpis": [
    {"id": "k1", "metric": "high_turnovers", "target": ">=6", "by_minute": 45},
    {"id": "k2", "metric": "final_third_entries_share", "params": {"channel": "right"}, "target": ">=0.40"},
    {"id": "k3", "metric": "set_piece_xg", "target": ">=0.30", "by_minute": 90}
  ],
  "plan_b": [
    {"if": {"kpi": "k1", "status": "failing", "after_minute": 30}, "then": {"press_height": "mid"}}
  ],
  "subs_plan": [{"window": "60-65", "out": "KES-7", "in": "KES-17"}],
  "valuation": "c_sim_21",
  "sealed": {"at": "14:58:03", "sha256": "3f9a…"}
}
```

### B.2 Claim
```json
{"claim_id": "c_sc_03", "type": "observed_tendency", "team": "HAR", "player_id": "HAR-3",
 "metric": "losses_per_100_pressured_receptions", "value": 31.7, "league_ref": 15.2,
 "n": 41, "matches": 8, "evidence": ["m03:e211", "m05:e098"], "status": "sufficient"}
```

### B.3 Tarjeta del descanso (antes del relleno)
```
EN (casual): "Their keeper stopped playing short at {c201.minute}'. Our press no longer wins the ball,
so the staff's best move is a mid block and the back post on corners ({c240.label})."
```

## Anexo C. Verificado frente a pendiente

**Verificado el 22 oct:**
- Bases oficiales (`microsoft/insidethegamehackathon`): criterios, categorías, requisitos de entrega, demo hasta el 10 nov y vídeo < 2 min.
- *The Dugout* (`lauramiro/the-dugout`): MIT, creado el 19 oct, 122 commits, desplegado, MCP público, ΔWP con *strong / lean / toss-up*, voto de 20 s, `/desk`, cue sheet, bifurcación contra la verdad, gancho NFL / F1.
- `bbenz/football-results-dashboard`: MIT, *"Deterministic analytics own every number"*.
- `Zidup123/ShapeShift`: ya no es público (404).
- Plazo: 23:59 PDT del 27 = 07:59 hora peninsular del 28.

**Pendiente de verificar el día 0:**
- Cuota y modelos disponibles en Foundry para nuestra suscripción.
- Versión y API de workflows de Microsoft Agent Framework.
- Retirada de los Workflows del portal de Foundry (afirmación de la v4).
- Cifras y fuentes de la tabla de calibración.
- Recuento de los 285 repositorios de la v4 (no reproducido).
