---
name: leasehold-analysis
description: "Assemble what a leasehold analysis needs on an AnnoLab abstract: leasing instruments (OGLs, assignments, partial and wellbore assignments, related instruments) from the county records, the user's own files, or other sources, plus wells and Oklahoma regulatory data (spacing, pooling). Use when the user wants to analyze leasehold, check who holds a lease, trace lease assignments, or determine whether leases are held by production."
---

# Leasehold analysis

Leasehold analysis asks who holds the working interest in a lease today and whether the lease is still alive. This skill gathers the inputs on an abstract and hands the examination to the user. It orchestrates existing tools and skills; it does not conclude title.

Resolve the abstract first (`list_projects` → `find_abstracts`; create with **abstract-intake** if it does not exist). Then offer the user the options below, in this order, and run the ones they pick.

## 1. Leasing instruments

What belongs in the set: oil and gas leases (OGLs, memoranda of lease, lease amendments, extensions, ratifications), assignments of every kind (assignment of oil and gas lease, partial assignment, wellbore assignment, assignment of overriding royalty, assignment of working interest), releases of lease, and anything else that affects the leasehold (farmouts, operating agreement memoranda, affidavits of production or non-production, lease-related liens).

Ask where the instruments should come from; any mix is fine:

- **County records search (Oklahoma).** Run the `annolab` MCP flow (`search_county_records` → `get_county_records_search` → `add_county_records_to_abstract`). Ask for the indexed date range first; never default it. Use the search's instrument-type counts to propose the set above. The user usually wants to pick the instruments themselves: as soon as `search_county_records` returns, give them the AnnoLab link from the response so they can select records there while the search finishes, and offer selecting here (by instrument type or specific records) as the alternative. Do not add records until the user has chosen one path and confirmed.
- **Files the user already has** (a landman's file, prior run sheets, scans on disk). Upload them with the **abstract-intake** skill, which asks the one question that matters — one instrument per file or several — and uploads through the SDK. Skip files the abstract already has.
- **Documents from another source** (a county or OCC imaging URL, an email attachment, another vendor). Have the user save them locally, then treat them as files above.

If some instruments came from the search and others from files, say so in the report so the user knows which were vetted against the county index.

## 2. Wells and regulatory data

Offer to bring in wells, completions, and Oklahoma spacing and pooling orders with the **regulatory-data** skill — from a provider (Convey640 today; other providers and states later) or from the user's own well lists and order PDFs, which that skill also covers. Spacing and pooling orders show the unit a lease is held within; wells show what is holding it.

## 3. Well activity

After wells are pulled, help the user decide which are active. Default rule: a well with production reported in the last 12 months is `active`; a well plugged or abandoned is `inactive`; anything else is `unknown` until the user decides. The user has the final say.

Summarize the decision rather than asking well by well. Group by evidence and propose one action per group, e.g. "6 wells last reported production in July 2026 — mark all active?", "2 wells are plugged — mark inactive", "3 wells have no production report — leave unknown, or mark inactive?". Apply the user's answers with `save_abstract_wells` (`wellStatus` per well, matched by `wellId` or `apiNumber`). Keep the evidence in each well's `properties` so the call can be revisited.

## Reporting

Instruments added (counts by type, link to the abstract), wells by status after the user's decisions, orders added by classification, and anything that needs a human: wells with uncertain locations, instruments the search could not classify, searches that returned nothing for a section.
