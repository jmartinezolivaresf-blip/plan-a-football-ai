# Submission text (draft)

**Project:** Plan A: The Battle of the Benches
**Category:** Best Multi-Agent System (choose "Best Use of Microsoft Foundry" only after a real, recorded Foundry run)
**Links:** demo URL (todo: deployment needs approval) · public repository (todo: owner flips visibility) · video (todo)

## One line

Two AI coaching staffs scout each other, seal their plans and make a blind half-time call; the broadcast then shows
what each bench believed next to what was really true.

## Description (about 220 words)

Football broadcasts explain what happened. Plan A explains the decisions behind it, and checks them.

Two coaching staffs, each a team of Microsoft Agent Framework agents (analyst, manager, half-time bench), work in
separate rooms. Each reaches the world only through its own Model Context Protocol server: past matches of a
synthetic league, a simulator to value plans, and a live Plan Tracker. Neither can see the other's options, beliefs
or choice; each anticipates the other from what it observed on the pitch. Plans are sealed before kick-off and
half-time choices are committed before the reveal.

At half-time each bench prices its three options against what it expects the other to do. Only after both seals
does the broadcast price the real payoff matrix, so viewers see a decision, the belief behind it and its regret,
with an interval.

Every number on screen is a claim with its sample size and likely range; agents write placeholders, never digits,
and code rejects ungrounded text. Inside our simulator, on seasons nobody inspected, scouting reports flag real
hidden weaknesses with 0.69 precision and 0.63 recall, and 9 of 12 sealed plans target a real weakness (a random
plan: about half). All data is synthetic; clubs and players are fictional.

## Why multi-agent

The duel needs agents with private information: one agent that saw both rooms could not anticipate, hide or regret.
Roles hand over through tools and claims, not shared memory, and the isolation is enforced by the host and tested.

## Before submitting

- [ ] Replace the "todo" links.
- [ ] Re-check every number against `eval/results/RESULTS.md` (generated) if the evaluation is re-run.
- [ ] Do not say the agents run on Microsoft Foundry unless `docs/FOUNDRY.md` records a real, verified run.
