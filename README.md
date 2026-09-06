# XOTLIST Agent Governance

AI agents produce code quickly. The harder problem is deciding **which agent is allowed to
change what, how another agent independently verifies it, what evidence constitutes
acceptance, and where human authority remains mandatory.**

This is the control plane I use to build and operate [XOTLIST](https://xotlist.com) with
several coding agents, and a real governed change taken from it.

Nothing here is a demonstration written after the fact. The artifacts in `examples/` are
production records, reproduced unedited. The verifier in `tools/` runs against them, and it
finds a genuine gap — see [What the verifier found](#what-the-verifier-found).

---

## The problem

One person directing five agents across four vendors runs into questions that don't arise
when a human writes the code:

- An agent that retries after a timeout will happily redo an irreversible action.
- An agent asked "did that work?" will answer from its own context, which is not evidence.
- An agent reviewing its own output finds it satisfactory with striking reliability.
- An agent given a hard acceptance criterion will meet an easier one and report success.

None of these are model failures. They are governance failures — the process permitted them.

## The model

```
                    ┌──────────────────────────────────────────┐
                    │  OWNING AUTHORITY (human)                │
                    │  · issues the mandate                    │
                    │  · sole acceptance and terminalisation   │
                    └────────────────┬─────────────────────────┘
                                     │  TASK
                                     │  assignee · authority_role
                                     │  forbidden_actions[]
                                     ▼
                    ┌──────────────────────────────────────────┐
                    │  AUTHOR AGENT                            │
                    │  · implements within the mandate         │
                    │  · submits RPT with content_sha256       │
                    │  · MAY NOT review or accept its own work │
                    └────────────────┬─────────────────────────┘
                                     │  RPT-nnnnnn
                                     ▼
                    ┌──────────────────────────────────────────┐
                    │  INDEPENDENT REVIEWER (different agent)   │
                    │  · verifies against the mandate           │
                    │  · pins the report hash it reviewed       │
                    │  · returns PASS or FAIL with findings     │
                    └────────────────┬─────────────────────────┘
                                     │  REV-nnnnnn
                                     ▼
                    ┌──────────────────────────────────────────┐
                    │  OWNER DISPOSITION                        │
                    │  · accepts, or returns for correction     │
                    │  · an operator may materialise this,      │
                    │    but may not author the judgement       │
                    └──────────────────────────────────────────┘
```

Roles are separated by agent, not by prompt. In the worked example below, `claude` authors,
`gravity` and `chatgpt` review independently, and `chatgpt` holds owning authority.

## What is actually enforced

Every task carries an explicit `forbidden_actions` list. These are the real values in use:

| Denial | Prevents |
|---|---|
| `SELF_REVIEW`, `GROK_SELF_REVIEW` | An agent marking its own work correct |
| `OWNER_ACCEPTANCE`, `TERMINALISATION` | An agent declaring itself finished |
| `LIVE_DATABASE_MUTATION`, `PRODUCTION_DATABASE_MUTATION`, `DIRECT_SQL_MUTATION` | Irreversible writes during authoring |
| `DEPLOYMENT`, `PRODUCTION_CODE_CHANGE`, `CANONICAL_INTEGRATION` | Shipping without acceptance |
| `SQLITE_AS_ACCEPTANCE_SUBSTITUTE`, `MARIADB_AS_ACCEPTANCE_SUBSTITUTE` | Proving it works on an easier engine than acceptance requires |
| `HISTORICAL_REWRITE`, `ACCEPTED_V4_SILENT_PATCH` | Quietly altering already-accepted history |

The substitution denials are the ones that came from being burned. An agent told to prove a
migration works will find the path of least resistance, demonstrate it on SQLite, and report
success in good faith.

### What counts as authority

Recorded on every owner disposition:

```
LOCAL_BRIDGESTORE_IS_AUTHORITY  = YES
DROPBOX_EXPORT_IS_NOT_AUTHORITY = YES
CHAT_MEMORY_IS_NOT_AUTHORITY    = YES
```

The third matters most. An agent's recollection of what it did is not evidence, however
confident. Only the store counts.

---

## The worked example

`examples/governed-change-001/` — a P4 contracts migration, `RPT-000120`.

```
TASK    P4-CONTRACTS-MIGRATIONS-A1-C1-CL1-C1-CX1-C2
        created_by chatgpt · assignee claude · authority_role OWNER
        forbidden: CANONICAL_INTEGRATION, LIVE_DATABASE_MUTATION, …
   │
   ▼
RPT-000120   submitted_by claude
             content_sha256 40438b11a7a247fd67c9161dca50fdee4b7db15a366e44bccb4d556099d93053
   │
   ├──► REV-000116   reviewer gravity   PASS
   └──► REV-000138   reviewer chatgpt   PASS   pins RPT-000120:40438b11…
```

Two independent reviewers, neither of them the author.

`examples/rejected-change-002/` — `REV-000125`, an owner FAIL disposition. `grok` authored,
`claude` reviewed and returned **FAIL** with two material findings, `chatgpt` dispositioned
the failure, and `grok` then materialised that decision while recording
`OPERATOR_EXERCISED_OWNER_JUDGEMENT = NO`.

The author report it rejects is **not** included in this bundle. The verifier reports that
absence rather than passing over it.

## Verifying it

```sh
python3 tools/verify_lineage.py
```

Checks four things:

1. Each report's `content_sha256` reproduces from its own body, and its sidecar `.md` is
   byte-identical. A content hash that does not reproduce is worse than no hash — it looks
   like evidence while proving nothing.
2. Each review pins the hash of the report it reviewed, and that hash matches the report as
   stored.
3. No agent reviews its own work — the machine check for `SELF_REVIEW`.
4. Artifacts referenced but absent are reported as absent.

## What the verifier found

Running it against the real records surfaces one genuine gap:

> **FINDING** — `REV-000116` (gravity) reviewed `RPT-000120` but cites only evidence IDs. No
> `evidence_ref` of the form `REPORT:sha256`, so the review is not pinned to a specific
> revision of what it reviewed.

`REV-000138` (chatgpt) reviewed the same report and *did* pin it. Two reviewers, two
conventions, one of them weaker.

That inconsistency is left visible rather than edited out, and the check that catches it is
kept as a hard check rather than softened into a pass. A governance tool that only ever
agrees with its own records is decoration.

Convention gaps are reported as findings and do not fail the run; broken invariants — a hash
that does not reproduce, a mismatched pin, a self-review — do.

## Scope

Derived from a production system. The task store, its API and its transport are not included;
this repository covers the model, the artifact schema and the verification, using real
records as the example.

Multi-agent governance frameworks exist. The claim here is not novelty — it is that this one
is concrete, in use, and evidenced by artifacts rather than described in the abstract.

## Licence

© William Ekuadzi. Published for review and demonstration. All rights reserved — not licensed
for reuse or redistribution.
