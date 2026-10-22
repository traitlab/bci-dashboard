#!/usr/bin/env bash
# Render diagrams/*.mmd to the light and dark SVGs the README embeds.
# GitHub's own mermaid sizes labels in the browser and clips them when it
# renders before layout, so the README ships SVG text drawn here instead.
set -euo pipefail
cd "$(dirname "$0")/../diagrams"
config=$(mktemp)
trap 'rm -f "$config"' EXIT
echo '{"htmlLabels": false, "flowchart": {"htmlLabels": false, "useMaxWidth": false}}' > "$config"
for src in *.mmd; do
  name=${src%.mmd}
  npx -y @mermaid-js/mermaid-cli@11.12.0 -q -c "$config" -t default -b white -i "$src" -o "$name.svg"
  npx -y @mermaid-js/mermaid-cli@11.12.0 -q -c "$config" -t dark -b '#0d1117' -i "$src" -o "$name-dark.svg"
done
