# Subagent fleet runbook — generic portable procedure

Status: generic portable procedure. The cross-profile native practice
described in `orchestration.md` §9 is verified only in a private local
fleet; no formal fleet-orchestration phase-machine is drafted here or in
§9. This document is the replicable unit: stages, contract shapes, gate
discipline, validators. It runs from a fresh clone with Python 3 stdlib +
bash only.

Audience: a stranger with a fresh clone on linux/macos/windows.

## 0. What this is and is not

- **Portable generic procedure (this document):** infrastructure-neutral
  stages, contract shapes, gate discipline, validators. Uses
  `{PLACEHOLDER}` tokens throughout.
- **Local private profile-native implementation (NOT shipped):**
  same-home profiles sharing one `$HOME`, native cross-profile writes
  into an orchestrator's delegation cache, single-writer lease files,
  per-profile model pins, in-home notification event streams. None of
  this exists on a stranger's machine and none of it is promised here.
- Anything below that the local fleet can do natively carries an
  explicit **LOCAL-ONLY** flag plus the portable fallback.

Sources: `choreography/orchestration.md` §§3–11; `choreography/artifact-contract.md`
+ `templates/contracts/artifact-contract.md.tmpl` + `build/check-artifact-contract.py`;
`templates/contracts/spawn-contract.md.tmpl` + `build/check-spawn-contract.py`;
`choreography/io-delegation.md` (bounded delegation, telemetry without payloads).

## 1. Ordered stages

Each stage: entry criteria (prior gate green) → deliverable path →
verification bar (read-back command) → restart budget → shutdown/escalation.

1. **Spawn.** Entry: spawn contract valid
   (`python3 build/check-spawn-contract.py <contract>` exit 0).
   Deliverable: one worker, one deliverable path, full context inline.
   Refuse-to-spawn: any required field empty/TBD → no dispatch.
   Restart: transient only, e.g. ≤3 restarts / 5 min, then escalate.
   **LOCAL-ONLY note:** local profile-native spawn (a session under one
   profile writing into a sibling profile's working directory) has no
   public equivalent; public spawn is a `delegate_task`-shaped dispatch
   with the spawn contract inline.
2. **Profile/model resolution.** Portable: enumerate the roster, print
   each value before/after with `{PROFILE}`/`{MODEL}` placeholders,
   apply per-profile, re-audit by script. Model choice follows the
   task's context/reasoning need. **LOCAL-ONLY note:** live
   per-profile model pins and rotation state are private; never ship
   live values.
3. **Process tracking.** Portable: append-only per-run ledger directory
   (`runs/{RUN_ID}/spawn.log`, `results.tsv`-style ledger);
   ledger-to-disk parity checked by machine count, not prose.
   **LOCAL-ONLY note:** single-writer lease files and dispatch/rotation
   ledgers are local-only; without them concurrent-write protection is
   advisory — say so in the run report.
4. **Return receipts.** Portable return path: **poll the durable
   artifact**. Every "done" carries a verifiable handle (relative path
   + checksum or ID) plus pasted verbatim read-back (command +
   output). Producer output is never evidence. Telemetry is
   route/bytes/latency/status, never payload. **LOCAL-ONLY note / hard
   limit:** separate-home oneshot processes do NOT emit `subagent.*`
   events and cannot use native steer; do not document events/steer as
   the public return path.
5. **Follow-ups.** A follow-up is a new dispatch with a corrected brief
   against the durable artifact, not a continuation of lost context.
   Carry `last_stable_phase` forward; never resume from memory.
6. **Steering.** Check-in cadence (minutes-scale): worker reports status
   + blocker-or-healthy; orchestrator steers on drift, stops on
   dead-end. Portable steering = re-dispatch with a corrected brief
   (restart per child-spec). **LOCAL-ONLY note:** live transcript
   intervention (native steer/stop of a live child in the same home)
   is not portable; say so explicitly.
7. **Monitor.** Milestone reports, never silence-then-timeout. The
   orchestrator owns cross-task drift; briefs make each room
   self-contained on cold start.
8. **Verify.** Producer/verifier separation: a different lane re-reads
   the artifact and grounds the verdict in pasted read-back.
   Served-truth: verify the served/live bytes, not the build log. Both
   contract validators must exit 0:
   `build/check-spawn-contract.py` and `build/check-artifact-contract.py`.
9. **Recovery.** Respawn loses in-context state → resume from the
   durable artifact at `resume_phase` (forward-only from
   `last_stable_phase`). Write-skeleton-first; artifact-sized scope;
   inline context. Plateau detector: past budget → escalate, never loop.
   Recovery drill: delete worker context (simulate respawn) →
   resume-from-artifact reproduces the deliverable path and re-passes
   its verification bar; budget exhaustion escalates instead of looping.
10. **Redaction.** Redact-first before any worker sees material: no
    secrets/credentials/private IDs/client data; external workers need
    operator approval; leak-scan before publish.

## 2. Contracts

- **Spawn contract:** `templates/contracts/spawn-contract.md.tmpl`
  (fields: `role_id / entry_gate / deliverable_path / verification_bar
  / restart_budget / timeout / resume_from / handoff_brief /
  stability`). Validated by `build/check-spawn-contract.py`.
- **Artifact handoff:** existing v1.5.0 schema unchanged
  (`choreography/artifact-contract.md`). No new fields without a
  validator update.
- **Return receipt** (read-back, pasted verbatim):

```
RECEIPT task={TASK_ID} phase={PHASE} profile={PROFILE}
command: {READBACK_CMD}
output:
{VERBATIM_OUTPUT}
artifact: {RELATIVE_PATH} sha256={CHECKSUM}
verdict: {PASS_OR_FAIL} by {VERIFIER_LANE} (not the producer)
```

## 3. Acceptance (fresh clone, all must pass)

- A-1 Fresh-clone reproduce: `bash scripts/fresh-clone-test.sh`
  passes with the new templates included.
- A-2 Contract validity: both checkers pass their worked examples and
  reject the invalid examples.
- A-3 Refuse-to-spawn: a spawn contract with any required field TBD is
  rejected (no dispatch).
- A-4 Honesty probes: (i) no native-steer/event claim in shipped text;
  (ii) this §0/§9-style status flag present wherever cross-profile
  practice is described; (iii) no live profile name, host path,
  session ID, or credential in the public surface (leak-scan exit 0).
- A-5 Recovery drill (see stage 9 above).
- A-6 Platform check: validators + example run on linux/macos
  (windows: validators at minimum), no new dependency beyond Python 3
  stdlib + bash.

## 4. Non-goals

No formal fleet-orchestration phase-machine (still pending per §9); no
routing/model-layer changes; no new runtime/hook/network client; no
local config edits; no live paths, profile names, session IDs, tokens,
or control-plane internals shipped. Portability rule: any shipped
path/command runs from a fresh clone on all three platforms or is
marked platform-conditional.
