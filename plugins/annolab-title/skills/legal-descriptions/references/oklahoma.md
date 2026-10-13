# Oklahoma — PLSS descriptions

Oklahoma is Public Land Survey System land. Descriptions locate a parcel by aliquot subdivision of a numbered section within a township and range, measured from a principal meridian.

## Structure

- **Principal meridian.** Most of Oklahoma is measured from the **Indian Meridian** (I.M.). The three panhandle counties — Cimarron, Texas, Beaver — use the **Cimarron Meridian** (C.M.). A description in a panhandle county that omits the meridian is ambiguous; flag it.
- **Township** runs north or south of the baseline: `21N`, `4S`. **Range** runs east or west of the meridian: `16W`, `3E`. The direction letter is part of the value.
- **Township** is nominally six miles square and contains **36 sections**.
- Sections are numbered boustrophedonically: section 1 in the northeast corner, running west to 6, then 7 directly below 6, running east to 12, and so on to 36 in the southeast corner.

## Aliquot parts

A regular section is nominally one square mile, 640 acres.

| Call | Acres | Note |
|---|---|---|
| Section | 640 | |
| Half (`N/2`, `E/2`) | 320 | |
| Quarter (`NE/4`) | 160 | |
| Half-quarter (`N/2 NE/4`) | 80 | |
| Quarter-quarter (`NE/4 NE/4`) | 40 | The standard "forty" |
| Quarter-quarter-quarter | 10 | Uncommon |

A regular section decomposes into **16 quarter-quarters**, which is the working unit for most mineral title.

Calls read smallest-to-largest. `SE/4 NW/4` is the southeast quarter of the northwest quarter — a 40-acre tract in the middle-north of the section.

## Government lots and irregular sections

**Sections are not reliably 640 acres.** Survey error and the convergence of meridians are absorbed at the north and west edges of each township. The affected sections — 1 through 6 across the north tier, and 7, 18, 19, 30, 31 down the west tier — carry **government lots** instead of regular quarter-quarters along those edges.

Consequences that matter:

- A government lot is identified by number (`Lot 1`, `Lot 2`), not by aliquot call, and has an irregular acreage fixed by the original survey — commonly in the 30s or low 40s, but it must be read, never assumed.
- A deed describing `NW/4 NW/4` in a section that actually carries `Lot 1` there is describing land by a call that may not exist as surveyed. Flag it.
- Nominal aliquot math is wrong in these sections. Take acreage from the plat or the instrument.
- Fractional sections also arise along state lines, river boundaries, and prior grants.

Water boundaries introduce accretion and avulsion questions that change acreage over time. These are legal conclusions — flag, do not resolve.

## Common abbreviations and variants

Normalize all of these:

- `NE/4`, `NE4`, `NE 1/4`, `NE¼`, `N.E. Quarter`, `Northeast Quarter` → `NE/4`
- `N/2`, `N2`, `N 1/2`, `N½`, `North Half` → `N/2`
- `SW/4 SE/4`, `SWSE`, `SW SE`, `SW/4 of the SE/4` → `SW/4 SE/4`
- `Sec. 15`, `Section 15`, `S15` → section `15`
- `T21N`, `Twp 21 North`, `21-N` → township `21N`
- `R16W`, `Rge 16 West`, `16-W` → range `16W`
- Compact forms: `15-21N-16W` → section 15, township 21N, range 16W

The compact `section-township-range` form is standard in Oklahoma runsheets and is usually safe to parse, but confirm the ordering against the document — some sources write township first.

## Oklahoma-specific title context

- **OCC spacing and pooling.** The Oklahoma Corporation Commission establishes drilling and spacing units by order, commonly 640 acres for deep formations. A **force pooling order** brings unleased or non-consenting interests into a unit. Pooled interests appear in title without a voluntary conveyance, so an owner can hold an interest with no deed in the chain — expect this and do not treat it as a gap.
- A spacing order can encompass an entire section regardless of tract boundaries, so unit-level and tract-level ownership are different questions. Keep them separate.
- **Depth severance** is common and often formation-referenced ("all depths below the base of the Chester"). A formation base is a surface that varies across a tract, not a flat datum. Capture the language verbatim; do not convert it to a numeric depth.
- **Held by production (HBP)** leases can survive decades past their primary term. A lease is not expired because its primary term ran — check production. Absence of a plugging record is not proof of production.

## Flags specific to Oklahoma

- Aliquot calls used in a section that carries government lots.
- A panhandle county description with no meridian stated.
- Township or range missing its direction letter.
- Acreage of record materially different from aliquot nominal acreage.
- An owner appearing with no conveyance in the chain — check for a pooling order before recording a gap.
