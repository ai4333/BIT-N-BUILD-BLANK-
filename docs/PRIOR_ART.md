# Prior art and what is ours

State the prior art first, credit it, and claim only what is unclaimed (SPEC §5). This file is
also the repository-hygiene register (§7.6): every external work we learn from gets a line.

## What we did not invent

| We did not invent | Who did | What they do not do |
|---|---|---|
| the conjunction network | Lewis, Newland, Swinerd & Saunders (2010), *Acta Astronautica* 66 | prescribe; cost it; attribute per operator |
| centrality on it | Lewis 2010; Rao (2023/24), arXiv:2410.04599 | prescribe, or cost it. Rao explicitly leaves optimal intervention as future work |
| orbital capacity modelling | MIT ARCLab MOCAT (MOCAT-SSEM, MOCAT-MC, pySSEM); D'Ambrosio & Linares, *JSR* | per-object, present-tense affordability |
| the orbital-use fee | Rao, Burgess & Kaffine (2020), *PNAS* 117(23) | compute one object's share from the catalogue |
| per-object risk ranking | McKnight et al.; LeoLabs top-50 most-concerning | rank by operational burden (they rank by Pc × mass) |
| collision avoidance products | Kayhan, Neuraspace, Slingshot, LeoLabs, COMSPOC | attribution or capacity |
| operator coordination | Kayhan Satcat; NASA Starling × SpaceX Starlink (2026); arXiv:2607.26570 | externality accounting |
| Pc methods | Foster (2D), Chan, Alfano; NASA CARA analysis tools | — (we implement Foster 2D + maximum-Pc, verified against Monte Carlo) |
| SGP4 | Vallado; `python-sgp4` (Brandon Rhodes) | — (a dependency) |
| the covariance-realism idea | ESA Kelvins Collision Avoidance Challenge (arXiv:2008.03069); `kesslerlib/kessler` | apply it to attribute burden |
| the two-peaks diagnosis | arXiv:2603.23552 (2026) | a decision system or an attribution ledger |

## What we built

The per-object **operational externality ledger** (manoeuvres forced, Δv extracted,
mission-days consumed from other operators, at a declared Pc threshold), and the decision
layer on top of it: keystone selection on the conjunction graph, WAIT/OBSERVE as first-class
actions priced by value of information, a free-form planner whose burns a deterministic
validator can reject, and a shell-level regime diagnostic κ.

## Software we depend on (normal dependencies, permissive licences)

| package | licence | role |
|---|---|---|
| `sgp4` | MIT | propagation |
| `skyfield` | MIT | time and frames (cross-validation) |
| `numpy`, `scipy` | BSD | linear algebra, optimisation, KD-tree spatial index |
| `networkx` | BSD | conjunction graph and centrality |
| `pandas`, `pyarrow` | BSD / Apache-2 | CDM dataset handling, caching |
| `fastapi`, `pydantic`, `uvicorn` | MIT | API |

## Repositories studied for technique only (no code included)

| repository | licence | what was learned |
|---|---|---|
| `markolivaic/kessler` | MIT | honest reporting of a dated snapshot; false-conjunction filters (docked/formation pairs) |
| `keanucz/detour` | MIT | LLM-proposes / physics-computes tool boundary |
| `esa/dSGP4` | GPL-3 (read only) | covariance propagation structure |
| `ARCLab-MIT/pyssem` | MIT | shell discretisation and species accounting for the capacity engine |
| `thkruz/keeptrack.space`, `satvisorcom/satvisor` | AGPL-3 (read only) | rendering ideas for the optional globe (P3); nothing used in the MVP |
