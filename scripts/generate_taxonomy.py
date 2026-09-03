#!/usr/bin/env python3
"""Generate the Literal enums that mirror API-side constant tables.

Reads, from a sibling checkout of the API repo:

- ``lib/prompts/content/oversight/taxonomy.ts`` -> ``BEHAVIOR_CODES`` (the
  category -> code table) into ``src/nope_net/_generated/oversight_taxonomy.py``
- ``lib/resources/classificationToScopes.ts`` -> ``SERVICE_SCOPES`` and
  ``POPULATIONS`` into ``src/nope_net/_generated/signpost_enums.py``

The TypeScript is regex-parsed (no Node needed): the tables are flat
``key: [ 'value', ... ]`` and ``key: 'value',`` literals. The generated files
are committed; re-run this script when the API tables change and commit the
result. ``--check`` exits non-zero when the committed output is stale.

Usage:
    python scripts/generate_taxonomy.py [--api-root ../api] [--check]
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = REPO_ROOT / "src" / "nope_net" / "_generated"

TAXONOMY_TS = Path("lib/prompts/content/oversight/taxonomy.ts")
SCOPES_TS = Path("lib/resources/classificationToScopes.ts")

_CATEGORY_RE = re.compile(r"^\s*([a-z_]+): \[\s*$")
_CODE_RE = re.compile(r"^\s*'([a-z_]+)',\s*$")
_ARRAY_END_RE = re.compile(r"^\s*\],?\s*$")
_KEY_VALUE_RE = re.compile(r"^\s*[a-z_]+: '([a-z_]+)',\s*$")


def _block(source: str, start_marker: str) -> List[str]:
    """Lines of the ``export const X = {`` ... ``} as const;`` block."""
    start = source.index(start_marker)
    end = source.index("} as const;", start)
    return source[start:end].splitlines()


def parse_behavior_codes(source: str) -> Dict[str, List[str]]:
    """Return ``{category: [codes...]}`` in source order from ``BEHAVIOR_CODES``."""
    table: Dict[str, List[str]] = {}
    current: str = ""
    for line in _block(source, "export const BEHAVIOR_CODES = {"):
        category = _CATEGORY_RE.match(line)
        if category:
            current = category.group(1)
            table[current] = []
            continue
        code = _CODE_RE.match(line)
        if code and current:
            table[current].append(code.group(1))
            continue
        if _ARRAY_END_RE.match(line):
            current = ""
    if not table:
        raise SystemExit("BEHAVIOR_CODES table not found or empty")
    return table


def parse_category_union(source: str) -> List[str]:
    """Members of ``export type BehaviorCategory = | 'a' | 'b';`` for a cross-check."""
    start = source.index("export type BehaviorCategory =")
    end = source.index(";", start)
    return re.findall(r"'([a-z_]+)'", source[start:end])


def parse_value_table(source: str, const_name: str) -> List[str]:
    """Values of a ``export const NAME = { key: 'value', ... } as const;`` table."""
    values: List[str] = []
    for line in _block(source, f"export const {const_name} = {{"):
        match = _KEY_VALUE_RE.match(line)
        if match:
            values.append(match.group(1))
    if not values:
        raise SystemExit(f"{const_name} table not found or empty")
    return values


def _literal(name: str, values: List[str]) -> str:
    lines = [f"{name} = Literal["]
    lines.extend(f'    "{v}",' for v in values)
    lines.append("]")
    return "\n".join(lines)


def _tuple(name: str, type_name: str, values: List[str]) -> str:
    lines = [f"{name}: Tuple[{type_name}, ...] = ("]
    lines.extend(f'    "{v}",' for v in values)
    lines.append(")")
    return "\n".join(lines)


def render_oversight(table: Dict[str, List[str]], source_path: str) -> str:
    categories = list(table)
    codes = [code for group in table.values() for code in group]
    by_category = ["OVERSIGHT_BEHAVIOR_CODES_BY_CATEGORY: Dict["]
    by_category.append("    OversightBehaviorCategory, Tuple[OversightBehaviorCode, ...]")
    by_category.append("] = {")
    for category, group in table.items():
        by_category.append(f'    "{category}": (')
        by_category.extend(f'        "{code}",' for code in group)
        by_category.append("    ),")
    by_category.append("}")
    parts = [
        '"""Oversight behaviour taxonomy: generated, do not edit.',
        "",
        f"Source: {source_path} (BEHAVIOR_CODES). Regenerate with",
        "``python scripts/generate_taxonomy.py``.",
        "",
        f"{len(codes)} behaviour codes across {len(categories)} categories. Request filters",
        "use these Literals; response ``code`` fields stay ``str`` so a taxonomy",
        "addition on the API never breaks parsing.",
        '"""',
        "",
        "from typing import Dict, Literal, Tuple",
        "",
        _literal("OversightBehaviorCategory", categories),
        "",
        _literal("OversightBehaviorCode", codes),
        "",
        _tuple("OVERSIGHT_BEHAVIOR_CATEGORIES", "OversightBehaviorCategory", categories),
        "",
        _tuple("OVERSIGHT_BEHAVIOR_CODES", "OversightBehaviorCode", codes),
        "",
        "\n".join(by_category),
        "",
    ]
    return "\n".join(parts)


def render_signpost(scopes: List[str], populations: List[str], source_path: str) -> str:
    parts = [
        '"""Signpost filter vocabularies: generated, do not edit.',
        "",
        f"Source: {source_path} (SERVICE_SCOPES, POPULATIONS). Regenerate with",
        "``python scripts/generate_taxonomy.py``.",
        "",
        f"{len(scopes)} service scopes and {len(populations)} populations. The API returns",
        "400 with ``invalid_scopes`` / ``invalid_populations`` for values outside these.",
        '"""',
        "",
        "from typing import Literal, Tuple",
        "",
        _literal("ServiceScope", scopes),
        "",
        _literal("Population", populations),
        "",
        _tuple("SERVICE_SCOPES", "ServiceScope", scopes),
        "",
        _tuple("POPULATIONS", "Population", populations),
        "",
    ]
    return "\n".join(parts)


def generate(api_root: Path) -> Dict[Path, str]:
    taxonomy_src = (api_root / TAXONOMY_TS).read_text(encoding="utf-8")
    table = parse_behavior_codes(taxonomy_src)
    union = parse_category_union(taxonomy_src)
    if sorted(union) != sorted(table):
        raise SystemExit(
            f"BehaviorCategory union {sorted(union)} differs from "
            f"BEHAVIOR_CODES keys {sorted(table)}"
        )
    scopes_src = (api_root / SCOPES_TS).read_text(encoding="utf-8")
    scopes = parse_value_table(scopes_src, "SERVICE_SCOPES")
    populations = parse_value_table(scopes_src, "POPULATIONS")
    return {
        GENERATED_DIR / "oversight_taxonomy.py": render_oversight(table, TAXONOMY_TS.as_posix()),
        GENERATED_DIR / "signpost_enums.py": render_signpost(
            scopes, populations, SCOPES_TS.as_posix()
        ),
    }


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-root",
        type=Path,
        default=REPO_ROOT.parent / "api",
        help="Path to the API repo checkout (default: ../api)",
    )
    parser.add_argument(
        "--check", action="store_true", help="Exit 1 if the committed output is stale"
    )
    args = parser.parse_args(argv)

    outputs = generate(args.api_root.resolve())
    stale: List[Tuple[Path, bool]] = []
    for path, content in outputs.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        stale.append((path, current != content))
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"wrote {path.relative_to(REPO_ROOT)}")
    if args.check:
        for path, is_stale in stale:
            print(f"{'STALE' if is_stale else 'ok   '} {path.relative_to(REPO_ROOT)}")
        return 1 if any(is_stale for _, is_stale in stale) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
