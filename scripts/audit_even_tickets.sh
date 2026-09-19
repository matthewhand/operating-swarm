#!/usr/bin/env bash
# Sequential even-ticket audit (#150..#682): for each ticket find the landing
# commit via log grep, then verify a touched artifact still exists in main.
set -u
cd ~/open-swarm-private
FROM=${1:-1}; TO=${2:-99999}
printf '%s\t%s\t%s\t%s\t%s\n' "issue" "state" "commit" "verdict" "artifact"
while IFS=$'\t' read -r num state title; do
  [ "$num" -ge "$FROM" ] && [ "$num" -le "$TO" ] || continue
  sha=$(git log --format='%h' --grep="#$num\b" -1 -- 2>/dev/null)
  commit="none"; verdict="NO-COMMIT-REF"; artifact=""
  if [ -n "$sha" ]; then
    commit="$sha"
    files=$(git show --name-only --format= "$sha" | head -6)
    ok=""; miss=""
    for f in $files; do
      [ -z "$f" ] && continue
      if git cat-file -e "main:$f" 2>/dev/null; then ok="$f"; break; else [ -z "$miss" ] && miss="$f"; fi
    done
    if [ -n "$ok" ]; then verdict="OK"; artifact="$ok";
    elif [ -n "$miss" ]; then verdict="ARTIFACT-REMOVED"; artifact="$miss";
    else verdict="MERGED-NO-FILES"; fi
  fi
  printf '%s\t%s\t%s\t%s\t%s\n' "$num" "$state" "$commit" "$verdict" "$artifact"
done < /tmp/evens.tsv
