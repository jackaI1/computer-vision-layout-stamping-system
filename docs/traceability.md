# Requirements traceability: design notes

These notes explain how `quality/rtm.py` works. The README gives the short version.

## Files

| File | Role |
| --- | --- |
| `quality/requirements.json` | The requirements, the one hand-kept source. Each has `code` (design elements) and `tests` (test name patterns). |
| `quality/rtm.py` | Command line: `check`, `coverage`, `diff`, `baseline`, `import`, `export`. |
| `quality/rtm_import.py` | Reads and writes CSV and ReqIF, and assigns stable IDs. |
| `quality/rtm_ids.json` | Registry of source key to project ID. Written by `import --write`. IDs are never reused. |
| `quality/baselines/*.json` | Saved snapshots of the requirements (`B1.json` is the first). |
| `quality/trace_matrix.py` | Existing generator. Reads test names with `ast` and resolves the `code` and `tests` links. `rtm.py` uses it, so both tools agree. |
| `examples/requirements/` | A three-requirement sample in CSV and ReqIF. |

## Rules checked by `check`

`check` runs four rules and prints one line per rule, in the style of a DOORS DXL
script that walks each object in a module:

- **R1** every requirement names at least one design element;
- **R2** every requirement has at least one automated test that exists;
- **R3** every design element and test pattern resolves to real code and real tests;
- **R4** every test in `tests/` is linked to at least one requirement (no orphan tests).

The command exits 1 when any rule fails. CI runs it in the `CI` workflow.

## Coverage matrix and baseline gaps

`coverage` prints one row per requirement with its status:

- `OK`, `UNTRACED` (no design element), `NO TEST`, `BROKEN LINK`, or `ORPHANED`
  (a removed requirement whose tests are still in the repository).

With `--baseline NAME` it adds a column that says whether the requirement was added
or changed since that baseline. `diff OLD [NEW]` lists the same changes and prints a
`GAP` line for each one that needs attention:

- a requirement added without a test;
- a requirement whose wording changed while its tests did not, so the test may no
  longer prove it;
- a requirement removed while its tests still exist.

## Stable IDs

`import` maps each source key (the `id` column, or the ReqIF `ID` value) to a project
ID:

1. a key seen before keeps its ID (from `quality/rtm_ids.json`);
2. a key equal to an existing project ID keeps that ID;
3. any other key gets the next free `REQ-nn`.

The next number is never lower than any number already used, so an ID that was
retired stays retired. An import dry-runs by default. With `--write` it adds new
requirements, updates changed ones, keeps the existing `code` and `tests` links when
the file leaves them empty, and writes the registry.

## ReqIF

ReqIF is the OMG exchange format for requirements, used by IBM DOORS and similar
tools. The reader takes each `SPEC-OBJECT` as one requirement and reads its
`ATTRIBUTE-VALUE-*` elements by the attribute definition's `LONG-NAME` (`ID`,
`Title`, `Text`, `Risk`, `Design element`, `Test`). The writer produces the same
names, so a file exported here can be read back. The stdlib XML parser is used; the
files are local exports, not untrusted input. Files from a real DOORS export may
use more attributes or types than this reader knows, and those are ignored.

## Limits

This is not a replacement for DOORS. It has no multi-user editing, no history of who
changed what, and no electronic signatures. It checks links between requirements, code
and tests. It does not decide whether a test really proves a requirement.
