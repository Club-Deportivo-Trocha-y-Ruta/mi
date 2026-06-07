# Quickstart: Validate & Maintain the Subagent Fleet Tiers

**Feature**: 005-subagent-model-tiers · **Date**: 2026-06-07

This feature is configuration-only. "Running" it means **validating the invariants** and
knowing how to **add a new agent** without breaking them.

## Validate the fleet (the contract test)

Run from the repo root. It checks: explicit model per agent, correct tier per role,
uniform color per team, five distinct team colors, and only recognized keys.

```bash
python3 - <<'PY'
import pathlib, re, sys
AG = pathlib.Path(".claude/agents")
LEADS = {"engineering-lead","head-coach-lead","family-relations-lead",
         "data-platform-lead","product-manager"}
TEAM_COLOR = {  # team -> color
 "Engineering":"blue","Sports/Head-Coach":"green","Data-Platform":"cyan",
 "Family-Communications":"orange","Product":"purple"}
# agent -> team
TEAM = {
 "engineering-lead":"Engineering","fastapi-architect":"Engineering","react-ui-engineer":"Engineering",
 "devops-engineer":"Engineering","qa-engineer":"Engineering","database-architect":"Engineering",
 "integration-engineer":"Engineering",
 "head-coach-lead":"Sports/Head-Coach","training-planner":"Sports/Head-Coach","nutrition-advisor":"Sports/Head-Coach",
 "injury-prevention-advisor":"Sports/Head-Coach","technique-coach":"Sports/Head-Coach",
 "mental-performance-coach":"Sports/Head-Coach","competition-strategist":"Sports/Head-Coach",
 "sports-science-advisor":"Sports/Head-Coach",
 "data-platform-lead":"Data-Platform","data-analyst":"Data-Platform","results-analyst":"Data-Platform",
 "data-privacy-guard":"Data-Platform","analytics-reporter":"Data-Platform",
 "family-relations-lead":"Family-Communications","parent-communicator":"Family-Communications",
 "event-coordinator":"Family-Communications","community-content-creator":"Family-Communications",
 "product-manager":"Product","ux-researcher":"Product","release-manager":"Product","technical-writer":"Product",
}
RECOGNIZED = {"name","description","tools","disallowedTools","model","color","memory",
 "permissionMode","maxTurns","skills","mcpServers","hooks","background","effort",
 "isolation","initialPrompt","color"}
errs=[]; seen_team_colors={}
files=sorted(AG.glob("*.md"))
files=[f for f in files if f.name!="README.md"]
for f in files:
    fm=f.read_text().split("---\n",2)
    if len(fm)<3: errs.append(f"{f.name}: no frontmatter"); continue
    d={}
    for line in fm[1].splitlines():
        m=re.match(r"([A-Za-z_]+):\s*(.*)$",line)
        if m: d[m.group(1)]=m.group(2).strip()
    name=d.get("name")
    for k in d:
        if k not in RECOGNIZED: errs.append(f"{name}: unrecognized key '{k}'")
    if name not in TEAM: errs.append(f"{name}: not in fleet mapping"); continue
    exp_model="opus" if name in LEADS else "sonnet"
    if d.get("model")!=exp_model: errs.append(f"{name}: model={d.get('model')} expected {exp_model}")
    exp_color=TEAM_COLOR[TEAM[name]]
    if d.get("color")!=exp_color: errs.append(f"{name}: color={d.get('color')} expected {exp_color}")
    seen_team_colors.setdefault(TEAM[name],set()).add(d.get("color"))
# distinct colors per team + across teams
for t,cs in seen_team_colors.items():
    if len(cs)!=1: errs.append(f"team {t}: mixed colors {cs}")
allcolors=[next(iter(cs)) for cs in seen_team_colors.values()]
if len(set(allcolors))!=len(allcolors): errs.append(f"color collision across teams: {allcolors}")
print(f"Checked {len(files)} agents.")
if errs:
    print("FAIL:"); [print("  -",e) for e in errs]; sys.exit(1)
print("PASS: all invariants hold (5 opus leads, 23 sonnet workers, 5 distinct team colors).")
PY
```

Expected output: `PASS: all invariants hold ...`

## Confirm only `model`/`color` changed (privacy/guardrail safety)

```bash
# Compare against the revision before this feature; only model/color lines should differ.
git diff <pre-change-rev> -- .claude/agents/'*.md' | grep -E '^[+-]' | grep -vE '^[+-]{3}' \
  | grep -vE '^[+-](model|color):' && echo "UNEXPECTED non-model/color changes ↑" \
  || echo "OK: only model/color lines changed"
```

## Add a new agent (keep invariants green)

1. Decide **role**: mostly delegates → lead (`model: opus`); mostly executes →
   worker (`model: sonnet`).
2. Pick the **team** and use its `color` (see `.claude/agents/README.md` or
   `contracts/agent-definition.frontmatter.md`). If it fits no team, extend the taxonomy
   in the README + contract first — never leave it uncolored/untiered.
3. Add the agent to the mapping in the README, the contract, and the validation script
   above.
4. Re-run the validation block — it must print `PASS`.

## Notes

- This is the AI-instruction corpus (English per constitution Principle III); it changes
  **no** product copy, code, or schema. No deploy, no migration.
- Safety is enforced by agent guardrails + RBAC + the constitution, independent of model
  tier — so re-tiering does not affect minors' privacy controls.
