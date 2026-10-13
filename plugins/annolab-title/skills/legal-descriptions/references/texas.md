# Texas — survey, abstract and block descriptions

**Texas is not PLSS land.** It retained its public lands on statehood and granted them under Spanish and Mexican colonial systems, the Republic, and later state programs. There is no township-and-range grid and no guaranteed section size.

Apply nothing from the Oklahoma reference here.

## How Texas land is identified

A Texas description locates land within an **original survey** (also called an original grant). The survey is identified by some combination of:

- **Survey name** — usually the original grantee, e.g. `T. J. Williams Survey`, `H&TC RR Co. Survey`.
- **Abstract number** — `A-123`, assigned by the county and **unique only within that county**. The same abstract number means different land in a different county, so an abstract number without a county is meaningless.
- **Block** — in much of West Texas, surveys were laid out in blocks by the railroad and land-script companies: `Block 34`, `Block T-5-S`, `Block M-21`.
- **Section within a block** — `Section 12, Block 34`.
- **League and labor** — Spanish-derived units used in the older grants. One **labor** is 177.1 acres; one **league** is 4,428.4 acres (25 labors).

A complete Texas call typically reads something like: *Section 12, Block 34, T-5-S, T&P RR Co. Survey, A-1187, Reeves County, Texas.*

## The trap: block-and-section is not PLSS

`Section 12, Block 34` reads like a PLSS call and behaves nothing like one.

- Sections in a Texas block are **not reliably 640 acres**. Block layouts vary by the granting company and era; sections of 640 are common in some blocks and absent in others.
- There is **no aliquot decomposition guarantee**. `NE/4` of a Texas section is meaningful only if the section is regular and the instrument uses that call — and even then the acreage must come from the survey or the deed, not from a formula.
- `Block` here is a survey grid identifier, not a PLSS township. It carries no north/south or east/west direction semantics.
- Do not attempt to locate a Texas section by township and range. Those fields do not exist.

When a Texas description uses quarter calls, treat them as descriptive subdivisions of a parcel whose total acreage is established elsewhere — by the survey, the plat, or the instrument's own recitation.

## Metes and bounds

A large share of Texas descriptions are metes and bounds: a beginning point tied to a monument or survey corner, followed by a sequence of courses (bearing and distance) closing back to the start.

- These **do not decompose into a call structure.** Do not force them. Carry them as an unparsed description with the full text preserved, plus whatever survey/abstract/county context is stated.
- Acreage comes from the instrument's recitation or a surveyor's computation. Never estimate it from the courses without running an actual closure calculation, and never present an estimate as the acreage of record.
- Flag any metes and bounds description whose stated acreage is absent, or that references a monument, plat, or adjoining tract not present in the file.

## Building AnnoLab AOIs for Texas

The AOI keys differ from PLSS. Use:

- `county` (required), `state` = `"TX"` (required)
- `block`, `abstract`, `survey`

Supply whatever the instrument states. `county` plus `abstract` is the most reliable pair, since abstract numbers are county-scoped. Do not populate `section`, `township`, or `range` for Texas — those are the PLSS keys and will not resolve.

## Normalization

- Abstract: accept `A-123`, `A 123`, `Abstract 123`, `Abst. No. 123` → `A-123`.
- Survey names: preserve the name as written, including railroad and company abbreviations (`T&P RR Co.`, `H&TC`, `GC&SF`). Do not expand or normalize them away — they are how the survey is indexed.
- Block: preserve the full identifier including any suffix (`T-5-S`, `M-21`). The suffix is part of the block name, not a township designation.
- Record the county on every parsed description. A Texas description without a county cannot be resolved.

## Texas-specific title context

- **Duhig** originates in Texas (*Duhig v. Peavy-Moore Lumber Co.*, 1940) and governs the effect of a reservation in a warranty deed that over-conveys. Recognize the fact pattern — a grantor reserving a fraction while warranting title to more than remains — and flag it with the arithmetic and instruments involved. Do not apply the doctrine and compute a result; that is a legal conclusion for an examiner.
- **Relinquishment Act lands** (surface owner acts as agent for the State's mineral interest on certain grants) create a split that is easy to miss. Flag any tract where the State of Texas appears as a mineral owner or the chain references the Relinquishment Act.
- **Mother Hubbard / catch-all clauses** are common and may reach land the description does not name.
- Mineral and royalty interests are distinct estates in Texas and are conveyed with different language. Do not collapse them.

## Flags specific to Texas

- PLSS fields populated on a Texas description.
- An abstract number with no county.
- A block-and-section call being treated as 640 acres or decomposed into aliquots.
- Metes and bounds with no recited acreage.
- A survey or abstract referenced in the chain that has no corresponding record in the file.
- State of Texas as a mineral owner, or any Relinquishment Act reference.
