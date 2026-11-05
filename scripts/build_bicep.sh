#!/usr/bin/env bash
# Compiles every Bicep template and parameter file in the repository (no Azure login or deployment).
# Linter rules come from templates/bicep/bicepconfig.json; rules set to "error" fail the build.
# Compiler type warnings (BCPxxx, e.g. a property the API version doesn't know) also fail it: ARM would
# ignore or reject that property at deployment. Style warnings from the linter are only reported.
#   bash scripts/build_bicep.sh
# Requires the Azure CLI (it installs Bicep with `az bicep install` if needed).
set -uo pipefail
cd "$(dirname "$0")/.."

az bicep install --only-show-errors >/dev/null 2>&1 || az bicep upgrade --only-show-errors >/dev/null 2>&1 || true
az bicep version

fail=0; count=0
while IFS= read -r f; do
  count=$((count + 1))
  case "$f" in
    *.bicepparam) cmd=(az bicep build-params --file "$f" --stdout) ;;
    *)            cmd=(az bicep build --file "$f" --stdout) ;;
  esac
  if out=$("${cmd[@]}" 2>&1 >/dev/null) && ! grep -q "Warning BCP" <<<"$out"; then
    warnings=$(grep -c "Warning" <<<"$out" || true)
    echo "PASS $f${warnings:+ ($warnings warnings)}"
    [[ -n "$out" ]] && sed 's/^/     /' <<<"$out"
  else
    echo "FAIL $f"
    sed 's/^/     /' <<<"$out"
    fail=$((fail + 1))
  fi
done < <(git ls-files '*.bicep' '*.bicepparam' | sort)

echo "Compiled $count files, $fail failed"
exit $((fail > 0))
