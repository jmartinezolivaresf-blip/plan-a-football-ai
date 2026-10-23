# Submission text (draft)

**Project:** Plan A: The Battle of the Benches
**Category:** Best Multi-Agent System (alternative: Best Use of Microsoft Foundry, only if the Foundry run is done)
**Links:** demo URL (todo, needs deployment approval) · public repository (todo, needs owner approval) · video (todo)

## One line

Two AI coaching staffs scout each other, seal their plans and make a blind half-time call; the broadcast then shows
what each bench believed next to what was really true.

## Description (about 200 words)

Football broadcasts explain what happened. Plan A explains the decisions behind it, and checks them.

Two coaching staffs, each a team of Microsoft Agent Framework agents (analyst, manager, half-time bench), work in
separate rooms. Each reaches the world only through its own Model Context Protocol server: past matches of a
synthetic league, a simulator to value plans, and a Plan Tracker during the match. Neither can see the other's
options, beliefs or choice. Plans are sealed before kick-off and half-time choices are committed before the reveal.

At half-time each bench prices its three options against what it thinks the other bench will do. Only after both
seals does the broadcast price the real payoff matrix, so viewers see a decision, the belief behind it and its
regret, with an interval.

Every number on screen is a claim with its sample size; agents write placeholders, never digits, and code rejects
ungrounded text. Inside our simulator, on seasons whose hidden traits were drawn at random and never inspected, we
measure how often scouting finds real weaknesses, whether plans target them (against random plans) and how many
expected points the AI benches' half-time calls lose (against always staying and choosing at random): results in
the repository's `eval/results/RESULTS.md`. All data is synthetic; clubs and players are fictional.

## Why multi-agent

The duel needs agents with private information: one agent that saw both rooms could not anticipate, bluff or regret.
Roles hand over through tools and claims, not shared memory, and the isolation is enforced by the host and tested.

## Before submitting

- [ ] Replace "todo" links. Check every number in this text against `eval/results/RESULTS.md`.
- [ ] Choose the category; "Best Use of Microsoft Foundry" only if the Foundry run is real and recorded.
