#!/usr/bin/env bash
# Decides what a push to main ships. Finds every PR merged by the push (one PR,
# or a whole stack merged at once), takes the highest version/* label among them
# and bumps from the latest release. No label anywhere -> nightly only.
#
# Also collects each PR's "## Deploy actions" section for the release notes; the
# server's deployer holds any release whose notes contain that heading.
#
# Env: GH_TOKEN, REPO, BEFORE, AFTER, IMAGE_NAME, INITIAL_VERSION, GITHUB_OUTPUT
set -euo pipefail

if [[ -z "${BEFORE:-}" || "$BEFORE" =~ ^0+$ ]]; then
  shas="$AFTER"
else
  shas="$(gh api "repos/$REPO/compare/$BEFORE...$AFTER" --jq '.commits[].sha')"
fi

prs="$(for sha in $shas; do
  gh api "repos/$REPO/commits/$sha/pulls" --jq '.[] | select(.merged_at != null) | .number'
done | sort -un)"

rank=0
notes=""
for pr in $prs; do
  labels="$(gh api "repos/$REPO/pulls/$pr" --jq '.labels[].name')"
  grep -qx 'version/patch' <<<"$labels" && (( rank < 1 )) && rank=1
  grep -qx 'version/minor' <<<"$labels" && (( rank < 2 )) && rank=2
  grep -qx 'version/major' <<<"$labels" && rank=3
  section="$(gh api "repos/$REPO/pulls/$pr" --jq '.body // ""' | tr -d '\r' \
    | awk '/^## +Deploy actions/{on=1; next} on && /^## /{on=0} on')"
  if [[ -n "$(tr -d '[:space:]' <<<"$section")" ]]; then
    title="$(gh api "repos/$REPO/pulls/$pr" --jq '.title')"
    notes+=$'\n'"### #$pr $title"$'\n'"$section"$'\n'
  fi
done
echo "Merged PRs in this push: ${prs:-none}; bump rank $rank"

delim="EOF_$(openssl rand -hex 8)"
emit() { printf '%s<<%s\n%s\n%s\n' "$1" "$delim" "$2" "$delim" >> "$GITHUB_OUTPUT"; }

if (( rank == 0 )); then
  echo "kind=nightly" >> "$GITHUB_OUTPUT"
  echo "version=nightly-${AFTER:0:7}" >> "$GITHUB_OUTPUT"
  emit tags "$IMAGE_NAME:nightly"
  exit 0
fi

latest="$(gh release view --repo "$REPO" --json tagName -q .tagName 2>/dev/null || true)"
if [[ -z "$latest" ]]; then
  new="$INITIAL_VERSION"
else
  IFS=. read -r major minor patch <<<"${latest#v}"
  case $rank in
    3) new="v$((major + 1)).0.0" ;;
    2) new="v$major.$((minor + 1)).0" ;;
    1) new="v$major.$minor.$((patch + 1))" ;;
  esac
fi
echo "Latest release: ${latest:-none}; new: $new"

echo "kind=release" >> "$GITHUB_OUTPUT"
echo "new_version=$new" >> "$GITHUB_OUTPUT"
echo "version=${new#v}" >> "$GITHUB_OUTPUT"
emit tags "$IMAGE_NAME:${new#v}"$'\n'"$IMAGE_NAME:latest"
if [[ -n "$notes" ]]; then
  emit deploy_actions "## Deploy actions"$'\n'"$notes"
else
  emit deploy_actions ""
fi
