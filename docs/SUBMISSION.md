# Submission checklist

Deadline: Tue 27 Oct 2026, 23:59 PT (Wed 28 Oct, 07:59 Spain). Judging until 10 Nov 2026: the demo must stay up and
public until then. Status column: done / todo / needs approval (owner decision before acting).

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Code complete on `main` (integration/h2 merged after both owners approve the contract changes) | needs approval | PR #3 ready for review; shared changes listed in its description (D-032..D-052) |
| 2 | CI green | done on PR #3 (1feac18) | re-check on `main` after the merge |
| 3 | Real Microsoft Foundry call verified and recorded | needs a personal subscription | code path tested against a Responses API mock; procedure in `docs/FOUNDRY.md` (`make foundry-check`, `make foundry-ping`) |
| 4 | Demo bundle frozen (seed, mode, git commit recorded in the bundle's eval.build) | done: seed 236, offline rules, b383a8e | after a Foundry run: seed search, bundle, `pipeline.story`, `pipeline.evidence`, re-record |
| 5 | Public demo URL (no login) | ready, needs a personal subscription | `infra/swa_deploy.sh` (Free plan, guards, anonymous verification); config checked in the SWA emulator |
| 6 | MCP server not exposed publicly | done | loopback only (D-026); the demo shows recorded traces |
| 7 | Repository public | needs approval | currently private; owner flips visibility at submission |
| 8 | README in English with run steps, architecture, data statement, results | done | add the demo URL when deployed |
| 9 | Evaluation results committed with what they mean and do not mean | done | `eval/results/RESULTS.md` (generated) |
| 10 | Video under 2 minutes, English | script + silent walkthrough | `docs/VIDEO_SCRIPT.md`, `docs/media/walkthrough.mp4`; narration still to record |
| 11 | No secrets in the repo | done 2026-10-24 | full-history scan: no keys/tokens/credential files; no internal subscription names; noreply author email. Re-run before flipping visibility |
| 12 | Fictional clubs/players only; no Premier League marks or data | done 2026-10-24 | club names are not Premier League or EFL clubs; player names are random first+last combinations (a coincidental match with a real person cannot be ruled out; the data statement says they are fictional); no logos or third-party media |
| 13 | GitHub Copilot usage log | todo | `docs/COPILOT_USAGE.md` is empty: fill only with real usage |
| 14 | Submission form text (pitch, category, links) | drafted | `docs/PITCH.md` |
| 15 | Final submit | needs approval | owner submits |
