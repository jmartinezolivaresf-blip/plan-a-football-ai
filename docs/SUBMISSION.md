# Submission checklist

Deadline: Tue 27 Oct 2026, 23:59 PT (Wed 28 Oct, 07:59 Spain). Judging until 10 Nov 2026: the demo must stay up and
public until then. Status column: done / todo / needs approval (owner decision before acting).

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Code complete on `main` (integration/h2 merged after both owners approve the contract changes) | needs approval | draft PR #3; D-032..D-045 list every contract and simulator change |
| 2 | CI green | done on PR #3 | re-check on `main` after the merge |
| 3 | Real Microsoft Foundry call verified and recorded | needs approval | `infra/AZURE_PLAN.md` step 1; then `python -m agents.foundry_ping` and `AGENTS_MODE=foundry make bundle` |
| 4 | Demo bundle frozen (seed, mode, git commit recorded in the bundle's eval.build) | done (offline rules) | regenerate with Foundry once item 3 is done, then re-run `python -m pipeline.story` |
| 5 | Public demo URL (no login) | needs approval | `infra/AZURE_PLAN.md` step 2: Static Web Apps Free, static files only |
| 6 | MCP server not exposed publicly | done | loopback only (D-026); the demo shows recorded traces |
| 7 | Repository public | needs approval | currently private; owner flips visibility at submission |
| 8 | README in English with run steps, architecture, data statement, results | done | add the demo URL when deployed |
| 9 | Evaluation results committed with what they mean and do not mean | done | `eval/results/RESULTS.md` (generated) |
| 10 | Video under 2 minutes, English | script drafted | `docs/VIDEO_SCRIPT.md`; record after the final bundle |
| 11 | No secrets in the repo | todo | re-run the secret scan before flipping visibility |
| 12 | Fictional clubs/players only; no Premier League marks or data | todo | names in `sim/season.py` re-checked against real clubs before publishing |
| 13 | GitHub Copilot usage log | todo | `docs/COPILOT_USAGE.md` is empty: fill only with real usage |
| 14 | Submission form text (pitch, category, links) | drafted | `docs/PITCH.md` |
| 15 | Final submit | needs approval | owner submits |
