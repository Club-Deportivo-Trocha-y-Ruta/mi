# UI routes and deep links (045)

## Coach

| Address | Destination |
|---|---|
| `/competitions` | Competencias list (season and filters in the URL, phase 0) |
| `/competitions/:id?tab=info\|results\|standings\|circuito\|insights` | Competition detail. `standings` only for cup válidas |
| `/competitions/:id?tab=conditions` | **Alias** → `?tab=circuito` |
| `/competitions/season/:year[?analisis=por-aprobar\|desactualizados]` | «Temporada» plus the analyses list (research R-11) |
| `/competitions/insights/season/:year` | **Redirect** → `/competitions/season/:year` |
| `/competitions/imports?seccion=cargas\|identidades\|sin-enlazar[&import=<id>]` | «Cargas e identidades» |
| `/competitions/history` | **Redirect** → `/competitions/imports?seccion=cargas` |
| `/competitions/identity-review` | **Redirect** → `/competitions/imports?seccion=identidades` |
| `/competitions/unlinked` | **Redirect** → `/competitions/imports?seccion=sin-enlazar` |
| `/competitions/import?import=<id>`, `/competitions/:id/import?import=<id>` | Import wizard **resumed** from a persisted import |
| `/athletes/:id?tab=races[&view=progresion\|analisis\|comparar][&insight=<iid>]` | Athlete «Carreras». Default view `progresion`; `insight` forces `analisis` and expands that analysis |
| `/athletes/:id?tab=ai_analysis[&insight=<iid>]` | **Alias** → `?tab=races&view=analisis[&insight=<iid>]` |
| `/athletes/:athleteId/race-analysis/insights/:iid` | **Alias** (phase 0) → `?tab=races&view=analisis&insight=<iid>` |

Unchanged legacy redirects: `/training/races/:id/club-insights` and `/coach/race-analysis`.

## Family

| Address | Destination |
|---|---|
| `/my-athletes/:id?tab=races[&view=progresion\|analisis][&insight=<iid>]` | Family «Carreras» |
| `/my-athletes/:id?tab=ai-analysis[&insight=<iid>]` | **Alias** → `?tab=races&view=analisis[&insight=<iid>]` |
| `/my-athletes/:id?tab=races&view=comparar` | Falls back to `view=progresion` (coach-only view; never an error) |
| `/parents/competitions/:raceEventId` | Family competition results (family metric subset) |

## Menu

- The area label is «Competencias». It contains three items: «Competencias» (list), «Temporada» and «Cargas e identidades».
- The «Cargas e identidades» badge = `identity_decisions_pending + imports_in_progress`.
