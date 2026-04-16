#!/usr/bin/env bash
# Recreate Cursor integration symlinks for vendored obra/superpowers (git submodule).
# Run after: git submodule update --init --recursive  OR  cd third_party/superpowers && git pull
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SP="${ROOT}/third_party/superpowers"
CURSOR="${ROOT}/.cursor"

if [[ ! -f "${SP}/skills/using-superpowers/SKILL.md" ]]; then
  echo "error: ${SP} missing or incomplete. Run: git submodule update --init --recursive" >&2
  exit 1
fi

mkdir -p "${CURSOR}/skills" "${CURSOR}/agents" "${CURSOR}/commands" "${CURSOR}/hooks"

for d in "${SP}"/skills/*/; do
  [[ -d "$d" ]] || continue
  base="$(basename "$d")"
  dest="${CURSOR}/skills/superpowers-${base}"
  rm -f "${dest}"
  ln -sfn "../../third_party/superpowers/skills/${base}" "${dest}"
done

rm -f "${CURSOR}/agents/superpowers-code-reviewer.md"
ln -sfn "../../third_party/superpowers/agents/code-reviewer.md" "${CURSOR}/agents/superpowers-code-reviewer.md"

for f in brainstorm execute-plan write-plan; do
  rm -f "${CURSOR}/commands/superpowers-${f}.md"
  ln -sfn "../../third_party/superpowers/commands/${f}.md" "${CURSOR}/commands/superpowers-${f}.md"
done

chmod +x "${CURSOR}/hooks/superpowers-session-start.sh"

HOOKS_JSON="${CURSOR}/hooks.json"
if [[ ! -f "${HOOKS_JSON}" ]]; then
  cat > "${HOOKS_JSON}" <<'EOF'
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      {
        "command": ".cursor/hooks/superpowers-session-start.sh"
      }
    ]
  }
}
EOF
else
  echo "note: ${HOOKS_JSON} already exists; not overwriting. Merge sessionStart to superpowers if needed." >&2
fi

echo "Superpowers Cursor integration updated under ${CURSOR}"
