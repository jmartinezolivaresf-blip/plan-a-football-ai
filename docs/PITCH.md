# Submission text (draft)

**Project:** Plan A: The Battle of the Benches
**Category:** Best Multi-Agent System (choose "Best Use of Microsoft Foundry" only after a real, recorded Foundry run)
**Links:** demo URL (todo: deployment needs a personal subscription) · public repository (todo: owner flips visibility) ·
video (todo: upload `docs/media/plan_a_demo_v2.mp4` with the recorded narration)

## One line

Two AI coaching staffs. Two hidden strategies. One tactical duel: each bench scouts, plans and makes a blind
half-time call, and the broadcast then shows what each bench believed next to what was really true.

## Description (about 220 words)

Football broadcasts explain what happened. Plan A explains the decisions behind it, and checks them.

Each club has its own AI staff, built with Microsoft Agent Framework: an analyst that scouts the opponent's last eight
matches and a manager that turns that evidence into a game plan, tested in simulation and locked in before kick-off.
The two staffs work in separate rooms. Each reaches the data only through its own Model Context Protocol tools, so
neither can see the other's plan, beliefs or choices; it can only read the other team from what happens on the
pitch.

At half-time both benches choose at the same moment, blind to each other. Each prices its options on what it
believes; the choices are locked in, then revealed. The simulator replays the second half hundreds of times for every
pair of choices, so viewers see the call, the belief behind it and what it cost, with a likely range.

Agents never type numbers: every figure on screen points to recorded data, and code rejects anything ungrounded.
Inside our simulator, on seasons nobody inspected, scouting flags real hidden weaknesses with 0.69 precision and 0.63
recall, and 9 of 12 plans target a real weakness (a random plan: about half). The half-time calls do not yet beat
random choices; we report that too. All data is synthetic; clubs and players are fictional.

## Why multi-agent

The duel needs agents with private information: one agent that saw both rooms could not anticipate, hide or regret.
Roles hand over through tools and claims, not shared memory, and the isolation is enforced by the host and tested.

## Before submitting

- [ ] Replace the "todo" links.
- [ ] Re-check every number against `eval/results/RESULTS.md` (generated) if the evaluation is re-run.
- [ ] Do not say the agents run on Microsoft Foundry unless `docs/FOUNDRY.md` records a real, verified run.
