# Gate G6: research-quality experiment

**Status:** not started.

## Commands

```bash
uv run pytest -q tests/evaluation tests/evolution
uv run episalpha experiment compare --campaign demo-v1 --runtime fake
uv run python scripts/diagnose.py
# plus the four standard checks, and one real-provider campaign
```

## Criteria

- [ ] Metrics have correct direction and denominators. Omission cannot win (A17). `N/A` is
      handled.
- [ ] Only the allowed patch passes. Forbidden edits are rejected and recorded (A16).
- [ ] Labels cannot be loaded from research or tool paths. A hash change blocks comparison
      (A24).
- [ ] Fake and real execution IDs are distinct, and fake results never satisfy live.
- [ ] **One real-provider campaign completed.** The free-tier schedule or credit decision is
      recorded.
- [ ] Stored: the manifest, label and evaluator hashes, all trial IDs (failed ones included),
      the actual comparison report, and the owner decision.
- [ ] An honest rejection is accepted as a valid result (A18). No invented improvement.
- [ ] The trial and decision events reconstruct the campaign from `episalpha.jsonl`.

## Results log (append-only; real output only)

_No runs yet._
