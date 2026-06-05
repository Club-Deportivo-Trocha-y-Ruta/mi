#!/usr/bin/env bash
# verify.sh — Translation invariant harness for feature 001-translate-claude-files-english
#
# Usage:
#   verify.sh <file-path>      — verify a single file
#   verify.sh --all-agents     — verify all .claude/agents/*.md
#   verify.sh --all-docs       — verify all docs/**/*.md
#   verify.sh --all            — verify CLAUDE.md + agents + docs
#
# Exit 0 if no failures; exit 1 if any check fails.
# Prints [PASS] / [FAIL] / [WARN] per check.
#
# Invariants implemented:
#   INV-2  Frontmatter integrity (agents only): name + description keys exist, YAML valid
#   INV-3  Structure parity: heading count, table rows, code fences vs. git HEAD baseline
#   INV-4  Residual Spanish prose scan (stopword grep)
#   INV-6  Relative .md link targets exist on disk
#   INV-7  git diff --name-only contains only allowed files

set -euo pipefail

# ---------------------------------------------------------------------------
# Repo root detection
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ---------------------------------------------------------------------------
# Allowed file set for INV-7 (relative to repo root)
# ---------------------------------------------------------------------------
ALLOWED_PATTERN="^(CLAUDE\.md|\.claude/agents/[^/]+\.md|docs/.*\.md|\.specify/memory/constitution\.md|specs/001-translate-claude-files-english/.*)$"

# ---------------------------------------------------------------------------
# Spanish stopwords for INV-4 (prose-level heuristic)
# Deliberately kept as a fixed list; proper nouns and intentional copy
# are excluded by the code-block / frontmatter stripping below.
# ---------------------------------------------------------------------------
STOPWORDS="el[[:space:]]|la[[:space:]]|los[[:space:]]|las[[:space:]]|de[[:space:]]|que[[:space:]]|para[[:space:]]|con[[:space:]]|sin[[:space:]]|segun[[:space:]]|atleta|entrenador|sesion"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
FAILURES=0
WARNINGS=0

pass()  { echo "[PASS] $*"; }
fail()  { echo "[FAIL] $*"; FAILURES=$((FAILURES + 1)); }
warn()  { echo "[WARN] $*"; WARNINGS=$((WARNINGS + 1)); }
info()  { echo "       $*"; }

# strip_prose <file>
# Removes YAML frontmatter, fenced code blocks, and inline code spans
# from a file, leaving only the surrounding prose. Used for INV-4.
strip_prose() {
    local file="$1"
    python3 - "$file" <<'PY'
import sys, re

content = open(sys.argv[1], encoding='utf-8').read()

# Remove YAML frontmatter (--- ... ---)
content = re.sub(r'^---\n.*?---\n', '', content, count=1, flags=re.DOTALL)

# Remove fenced code blocks (``` or ~~~ fences)
content = re.sub(r'```[^\n]*\n.*?```', '', content, flags=re.DOTALL)
content = re.sub(r'~~~[^\n]*\n.*?~~~', '', content, flags=re.DOTALL)

# Remove inline code spans (`...`)
content = re.sub(r'`[^`]+`', '', content)

# Remove HTML comments
content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)

# Remove URLs in markdown links [text](url) — keep the text
content = re.sub(r'\]\([^)]+\)', ']', content)

print(content)
PY
}

# count_headings <file>
count_headings() { grep -c "^#" "$1" 2>/dev/null || echo 0; }

# count_table_rows <file>  (lines starting with |)
count_table_rows() { grep -c "^|" "$1" 2>/dev/null || echo 0; }

# count_code_fences <file>  (opening ``` or ~~~ lines)
count_code_fences() {
    # Count fenced blocks as opening fences only (every pair = 1 block, but we
    # count raw fence lines for parity with baseline; opening = line starting
    # with ``` or ~~~ possibly followed by language tag)
    { grep -c "^\`\`\`" "$1" 2>/dev/null || echo 0; }
}

# git_show_head <file-relative-to-repo-root>
# Returns HEAD content of a file (empty string if file is new/untracked).
git_show_head() {
    local rel="$1"
    git -C "${REPO_ROOT}" show "HEAD:${rel}" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# INV-2 — Frontmatter integrity (agents only)
# ---------------------------------------------------------------------------
check_inv2() {
    local file="$1"
    echo "  INV-2: frontmatter integrity"

    if ! python3 - "$file" <<'PY'
import sys, re, yaml

content = open(sys.argv[1], encoding='utf-8').read()
parts = content.split('---', 2)
if len(parts) < 3:
    print("ERROR: no YAML frontmatter block found")
    sys.exit(1)

fm_raw = parts[1]
try:
    fm = yaml.safe_load(fm_raw)
except yaml.YAMLError as e:
    print(f"ERROR: YAML parse error: {e}")
    sys.exit(1)

if not isinstance(fm, dict):
    print("ERROR: frontmatter is not a mapping")
    sys.exit(1)

if 'name' not in fm:
    print("ERROR: missing key 'name'")
    sys.exit(1)

if 'description' not in fm:
    print("ERROR: missing key 'description'")
    sys.exit(1)

if not isinstance(fm['description'], str) or not fm['description'].strip():
    print("ERROR: 'description' is empty or not a string")
    sys.exit(1)

print(f"OK name={fm['name']!r}")
PY
    then
        fail "INV-2: $file — frontmatter invalid (see output above)"
        return
    fi
    pass "INV-2: $file"
}

# ---------------------------------------------------------------------------
# INV-3 — Structure & section parity vs. git HEAD
# ---------------------------------------------------------------------------
check_inv3() {
    local file="$1"
    local rel="${file#"${REPO_ROOT}/"}"
    echo "  INV-3: structure parity (headings / table rows / code fences)"

    local head_content
    head_content="$(git_show_head "${rel}")"

    if [[ -z "${head_content}" ]]; then
        warn "INV-3: $rel — no HEAD version found (new file?); skipping parity check"
        return
    fi

    # Write HEAD content to a temp file for comparison
    local tmp_head
    tmp_head="$(mktemp /tmp/verify_head_XXXXXX.md)"
    printf '%s' "${head_content}" > "${tmp_head}"

    local h_cur h_head t_cur t_head f_cur f_head
    h_cur="$(count_headings "${file}")"
    h_head="$(count_headings "${tmp_head}")"
    t_cur="$(count_table_rows "${file}")"
    t_head="$(count_table_rows "${tmp_head}")"
    f_cur="$(count_code_fences "${file}")"
    f_head="$(count_code_fences "${tmp_head}")"

    rm -f "${tmp_head}"

    local ok=true

    if [[ "${h_cur}" -ne "${h_head}" ]]; then
        fail "INV-3: $rel — heading count changed: HEAD=${h_head}, current=${h_cur}"
        ok=false
    fi
    if [[ "${t_cur}" -ne "${t_head}" ]]; then
        fail "INV-3: $rel — table row count changed: HEAD=${t_head}, current=${t_cur}"
        ok=false
    fi
    if [[ "${f_cur}" -ne "${f_head}" ]]; then
        fail "INV-3: $rel — code fence count changed: HEAD=${f_head}, current=${f_cur}"
        ok=false
    fi

    if [[ "${ok}" == "true" ]]; then
        pass "INV-3: $rel (headings=${h_cur}, table-rows=${t_cur}, fences=${f_cur})"
    fi
}

# ---------------------------------------------------------------------------
# INV-4 — No residual untranslated prose (Spanish stopword scan)
# ---------------------------------------------------------------------------
check_inv4() {
    local file="$1"
    local rel="${file#"${REPO_ROOT}/"}"
    echo "  INV-4: residual Spanish prose scan"

    # Strip code blocks / frontmatter so we only look at prose
    local prose
    prose="$(strip_prose "${file}")"

    local hits
    hits="$(printf '%s' "${prose}" | grep -inE "${STOPWORDS}" || true)"

    if [[ -z "${hits}" ]]; then
        pass "INV-4: $rel — 0 Spanish stopword matches in prose"
    else
        local count
        count="$(printf '%s\n' "${hits}" | wc -l | tr -d ' ')"
        warn "INV-4: $rel — ${count} potential residual-Spanish line(s) (review required):"
        printf '%s\n' "${hits}" | head -20 | while IFS= read -r line; do
            info "  >> ${line}"
        done
        if [[ "${count}" -gt 20 ]]; then
            info "  ... (truncated; run grep manually for full list)"
        fi
    fi
}

# ---------------------------------------------------------------------------
# INV-6 — Relative .md link resolution
# ---------------------------------------------------------------------------
check_inv6() {
    local file="$1"
    local rel="${file#"${REPO_ROOT}/"}"
    local file_dir
    file_dir="$(dirname "${file}")"
    echo "  INV-6: relative .md link resolution"

    # Extract relative .md links (not http:// or https://)
    local links
    links="$(grep -oE '\]\(([^)]+\.md)' "${file}" | grep -v 'http' | sed 's/\](\(.*\)/\1/' || true)"

    if [[ -z "${links}" ]]; then
        pass "INV-6: $rel — no relative .md links found"
        return
    fi

    local broken=0
    local checked=0
    while IFS= read -r link; do
        # Strip anchor fragments (#section)
        local target="${link%%#*}"
        [[ -z "${target}" ]] && continue

        # Resolve relative to file's directory (portable: no realpath -m on macOS)
        local resolved
        resolved="$(python3 -c "import os,sys; print(os.path.normpath(os.path.join(sys.argv[1], sys.argv[2])))" "${file_dir}" "${target}" 2>/dev/null || echo "")"

        checked=$((checked + 1))
        if [[ -z "${resolved}" ]] || [[ ! -f "${resolved}" ]]; then
            fail "INV-6: $rel — broken link: ${link} (resolved: ${resolved:-<empty>})"
            broken=$((broken + 1))
        fi
    done <<< "${links}"

    if [[ "${broken}" -eq 0 ]]; then
        pass "INV-6: $rel — ${checked} relative .md link(s) all resolve"
    fi
}

# ---------------------------------------------------------------------------
# INV-7 — Out-of-scope files guard
# ---------------------------------------------------------------------------
check_inv7() {
    echo "  INV-7: out-of-scope files guard (git diff --name-only HEAD)"

    local changed_files
    changed_files="$(git -C "${REPO_ROOT}" diff --name-only HEAD 2>/dev/null || true)"

    if [[ -z "${changed_files}" ]]; then
        pass "INV-7: no files changed vs. HEAD"
        return
    fi

    local violations=0
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        if ! echo "${f}" | grep -qE "${ALLOWED_PATTERN}"; then
            fail "INV-7: out-of-scope file modified: ${f}"
            violations=$((violations + 1))
        fi
    done <<< "${changed_files}"

    if [[ "${violations}" -eq 0 ]]; then
        pass "INV-7: all ${changed_files//[^$'\n']/x} changed file(s) are in-scope"
    fi
}

# ---------------------------------------------------------------------------
# Run all checks for a single file
# ---------------------------------------------------------------------------
verify_file() {
    local file="$1"

    if [[ ! -f "${file}" ]]; then
        fail "File not found: ${file}"
        return
    fi

    echo ""
    echo "=== Verifying: ${file#"${REPO_ROOT}/"} ==="

    # INV-2 only for agent files
    if echo "${file}" | grep -q "\.claude/agents/"; then
        check_inv2 "${file}"
    fi

    check_inv3 "${file}"
    check_inv4 "${file}"
    check_inv6 "${file}"
}

# ---------------------------------------------------------------------------
# Argument parsing and dispatch
# ---------------------------------------------------------------------------
if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <file-path> | --all-agents | --all-docs | --all"
    exit 1
fi

FILES_TO_CHECK=()

case "$1" in
    --all-agents)
        while IFS= read -r f; do
            FILES_TO_CHECK+=("$f")
        done < <(find "${REPO_ROOT}/.claude/agents" -name "*.md" | sort)
        ;;
    --all-docs)
        while IFS= read -r f; do
            FILES_TO_CHECK+=("$f")
        done < <(find "${REPO_ROOT}/docs" -name "*.md" | sort)
        ;;
    --all)
        FILES_TO_CHECK+=("${REPO_ROOT}/CLAUDE.md")
        while IFS= read -r f; do
            FILES_TO_CHECK+=("$f")
        done < <(find "${REPO_ROOT}/.claude/agents" -name "*.md" | sort)
        while IFS= read -r f; do
            FILES_TO_CHECK+=("$f")
        done < <(find "${REPO_ROOT}/docs" -name "*.md" | sort)
        ;;
    -*)
        echo "Unknown option: $1"
        echo "Usage: $0 <file-path> | --all-agents | --all-docs | --all"
        exit 1
        ;;
    *)
        # Single file — resolve to absolute path
        if [[ "$1" = /* ]]; then
            FILES_TO_CHECK+=("$1")
        else
            FILES_TO_CHECK+=("${REPO_ROOT}/$1")
        fi
        ;;
esac

# Run per-file checks
for f in "${FILES_TO_CHECK[@]}"; do
    verify_file "${f}"
done

# INV-7 is always run (it checks the whole working tree, not per-file)
echo ""
echo "=== INV-7: Global out-of-scope guard ==="
check_inv7

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
echo "Summary: ${FAILURES} failure(s), ${WARNINGS} warning(s)"
if [[ "${FAILURES}" -gt 0 ]]; then
    echo "RESULT: FAIL"
    exit 1
else
    echo "RESULT: PASS"
    exit 0
fi
