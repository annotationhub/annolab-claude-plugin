---
name: legal-descriptions
description: "Parse, normalize, validate and compare land legal descriptions in Oklahoma and Texas — aliquot PLSS calls, government lots, block/survey/abstract descriptions, and metes and bounds. Use when reading a description off a deed, lease or runsheet, building AnnoLab AOIs, computing gross acreage, or checking whether two descriptions cover the same land."
---

# Legal descriptions (OK / TX)

Turn written land descriptions into structured, comparable data. This is the input to everything else in a title file: acreage, overlap, chain scoping, and AnnoLab AOIs all depend on getting the description right.

## Route by survey system first

Read the state before reading the description. The two systems are structurally different and share vocabulary in ways that mislead.

| State | System | Read |
|---|---|---|
| Oklahoma | PLSS — section / township / range, aliquot parts, government lots | `references/oklahoma.md` |
| Texas | Block / survey / abstract, leagues and labors, metes and bounds | `references/texas.md` |

Load the relevant reference file before parsing anything non-trivial. Do not guess at conventions from the other system.

**The trap that costs the most:** a Texas description reading `Section 12, Block 34, T-5-S` looks like PLSS and is not. Texas has no PLSS. Block-and-section there is a survey grid with no guaranteed 640-acre section, no aliquot decomposition, and no township/range meaning. Never apply PLSS math to a Texas description.

## The canonical form is the call, not the polygon

Store the **parsed call** as the canonical representation of what an instrument describes. Derive geometry from it for spatial work; never let geometry become the identity.

- Two instruments describing `NE/4 NE/4` of the same section describe the *same land*. They compare equal as calls. As polygons they may differ by survey tolerance, which produces slivers and near-matches an agent will reason about incorrectly.
- Use calls for identity, equality, and set operations on aliquot parts.
- Use geometry for intersection, proximity, and anything crossing section or survey lines.
- When a description cannot be parsed into a call (most metes and bounds), say so explicitly and carry it as unparsed rather than forcing it into a structure it doesn't fit.

## Acreage: three different numbers

Keep these distinct. Conflating them produces net mineral acre errors that survive every downstream check.

1. **Nominal acreage** — what the aliquot math implies. `NE/4 NE/4` = 40 acres. Correct only for regular sections.
2. **Acreage of record** — what the instrument itself recites ("containing 40 acres, more or less"). This is what the granting language operates on, and it governs interest computation unless the instrument says otherwise.
3. **Surveyed / computed acreage** — what the actual geometry measures. A government lot may compute to 38.42 acres while conveying as 40.

Report acreage of record when reproducing an instrument. Report computed acreage when measuring ground. Never silently substitute one for the other, and flag any tract where they diverge by more than a rounding artifact.

## Normalization rules

Normalize on parse, and keep the original string alongside the structure.

- Quarter calls: accept `NE/4`, `NE4`, `NE 1/4`, `NE¼`, `Northeast Quarter` → emit `NE/4`.
- Order calls smallest-to-largest: `SE/4 NW/4` is the southeast quarter *of* the northwest quarter.
- Expand halves explicitly: `E/2 SE/4` → `NE/4 SE/4` + `SE/4 SE/4` when a quarter-quarter set is needed.
- Township and range carry a direction: `21N`, `16W`. Preserve it; a bare `21` is ambiguous and must be flagged, not defaulted.
- Record the principal meridian when stated. In Oklahoma this is usually the Indian Meridian; the panhandle counties use the Cimarron Meridian, and a description that omits it in a panhandle county is a flag.
- Capture `LESS AND EXCEPT` clauses as a separate exclusion set, never by editing the base call.
- Capture depth limitations (`all depths below the base of the Chester`, `surface to 5,000 feet`) as a separate depth interval. Depth is part of what an instrument covers — a description without it is incomplete for mineral work.

## Building AnnoLab AOIs

Once parsed, create the abstract with the `create_abstract` tool on the `annolab` MCP server; its `aois` parameter schema is the authoritative field list (`county` and two-letter `state` always; `section`/`township`/`range` outside Texas, `section`/`block`/`abstract`/`township`/`survey` in Texas — the tool rejects fields from the other system).

One AOI per section or survey. A description spanning multiple sections becomes multiple AOI entries, not one entry with a compound string. Read the AOIs back in plain terms and get confirmation before calling the tool.

## What to flag rather than decide

Recognize and escalate these patterns. Do not adjudicate them — they are legal conclusions and belong to an examiner.

- A reservation or exception that conveys more than the grantor appears to hold (the Duhig fact pattern). Flag the arithmetic and the instruments involved; do not apply a doctrine and compute a result.
- A "Mother Hubbard" or catch-all clause ("all lands owned by grantor in said county"), which may reach land the description doesn't name.
- A description referencing a survey, plat, or instrument not in the file.
- Acreage of record that disagrees materially with the aliquot or surveyed figure.
- A call that cannot be located within the stated section or survey.
- Any description in a section known to be irregular (see the Oklahoma reference on government lots) where the instrument uses regular aliquot calls.

Emit each as a structured exception with the evidence and the acres at risk, ranked so the largest exposure is reviewed first.

## Working discipline

- Parse in a script. Print a summary — counts by system, unparsed descriptions, flagged patterns — not the descriptions themselves.
- When comparing many descriptions, compute the comparison in code and report only the matches, conflicts, and gaps.
- Never estimate acreage that can be computed or read off an instrument.
