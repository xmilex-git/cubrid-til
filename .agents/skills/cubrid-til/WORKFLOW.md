# Workflow

## Session lifecycle

### 1. Recover or open

- Read `Learning State.md` before selecting a topic.
- Resume an `in-progress` session before opening another unless the user explicitly defers it.
- Name sessions `YYYY-MM-DD-NNN Topic.md` under `08 Discussion Sessions/`.
- Record the source checkout remote, branch, and commit at session start.

### 2. Clarify

For each user statement:

1. Restate the claim precisely.
2. Identify overloaded terms, hidden assumptions, and scope.
3. Search existing notes before creating a new note.
4. Explore source code or project documents for answerable facts.
5. Ask exactly one unresolved question and include a recommendation.
6. Save the resulting state before continuing.

Do not preserve a verbatim transcript by default. Preserve a faithful structured summary, including corrections and unresolved disagreement.

### 3. Verify

Implementation claims require:

- source repository and exact commit;
- file path and symbol;
- the smallest useful code excerpt;
- explanation of observable behavior and constraints;
- release in which the behavior was introduced when discoverable.

Do not infer historical intent from code silently. When direct rationale is absent, use this order:

1. Observe code, tests, schema, call paths, and invariants.
2. Search commit, issue, PR, release note, manual, and ADR evidence.
3. State the inferred rationale separately.
4. List plausible alternative hypotheses.
5. State what evidence would disprove the inference.
6. Assign `high`, `medium`, or `low` confidence.

### 4. Complete

A topic is `completed` only when all are present:

1. An explanation understandable to a backend developer new to DB internals.
2. A concrete normal or failure scenario.
3. Relevant CUBRID code path and minimal excerpt.
4. Official-release-based `recent` or `historical` classification.
5. Facts and inference separated.
6. Unknowns and confidence recorded.
7. Prerequisite, follow-up, and related wikilinks.
8. The user's central opinion and corrections reflected.

Completion means the current question is adequately answered, not that the subject can never change.

### 5. Expand breadth-first

Maintain three independent BFS tracks:

- `engine`: concepts, architecture, and code;
- `development`: process, tests, and review;
- `operations`: observability, operation, and troubleshooting.

Each frontier item records `depth`, prerequisites, recommendation count, and state. Recommend exactly one eligible item from each track. Prefer the shallowest incomplete depth; break ties by prerequisite value, current-topic relation, practical usefulness, graph gap, then user interest.

Candidate outcomes are `selected`, `deferred`, or `rejected`. Never discard previous recommendations from the state history.

When the user says “나중에 다루자”, “별도로 보자”, or otherwise postpones a discovered branch, enqueue it immediately in `후속 주제 큐`. Record:

- canonical topic or provisional title;
- track and tentative depth;
- source session and why it matters;
- prerequisites and blocking unknowns;
- mention count and `queued` state.

Merge duplicate queue entries instead of appending synonyms; preserve every source session and increment the mention count. A queued topic does not bypass BFS. Promote it to `BFS Frontier` only when its prerequisites are complete and its depth is eligible. Queue states are `queued | frontier | selected | completed | rejected`.

### 6. Save and publish

After every user answer, update the session note and `Learning State.md`; update canonical notes whenever a fact is resolved. This makes abrupt termination recoverable.

At normal close:

1. Run `python3 .agents/skills/cubrid-til/scripts/validate_vault.py .`.
2. Inspect the changed-file list and stage only files changed by this session.
3. Commit with `knowledge: <topic and outcome>`.
4. Run `git fetch origin`.
5. If behind, run `git pull --rebase origin <branch>`.
6. On conflict, abort the rebase, keep the local commit, and record `sync-blocked`.
7. Push without force.

## Confidentiality

Default to `visibility: internal`. Never save credentials, tokens, private keys, personal data, customer-identifying data, real production addresses, or account names. Replace infrastructure identifiers with placeholders. Mark unpublished vulnerabilities `restricted`; validation blocks them from automatic push.

Private storage is not a reason to ignore future publication. A future public conversion requires reviewing every `internal` note and resolving all validator warnings.