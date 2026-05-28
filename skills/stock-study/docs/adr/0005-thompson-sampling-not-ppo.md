# ADR-0005 · Thompson Sampling Champion-Challenger, not PPO RL

**Status**: Accepted (2026-05-25)
**Decider**: 王选策, 张涛, 陈夏童

## Context

v3.0 proposed using PPO (Proximal Policy Optimisation) for closing the Champion-Challenger loop on factor selection. Audit red-team P1-4 flagged: (a) PPO requires thousands of episodes; we have ~250 trading days/year per regime, (b) reward shaping with financial KPIs is notoriously hard, (c) PPO has reward-hacking failure modes that buy-side teams have well-documented.

## Decision

Use **Thompson Sampling Beta-Binomial bandit** for the Champion-Challenger loop:

- Two arms: champion (current production factor set) and challenger (proposed by Agent-ZT).
- Reward: binary — daily IC > 0.04 ⇒ success, else failure.
- Prior: Beta(1, 1) — weakly informative.
- Posterior update after each day.
- Promotion gate: `P(challenger > champion | data) ≥ 0.90` AND `n_challenger_trials ≥ 20`.
- **Human sign-off still required** (D10) — bandit recommends, CEO approves.

Code lives in `evals/bandit.py` (skeleton; full implementation in S4).

## Consequences

**Positive**
- Sample-efficient: handles ~20-trial promotions
- No reward shaping pitfalls — binary outcome is unambiguous
- Computationally trivial (`np.random.beta`, no GPU, no episode replay)
- Battle-tested in advertising / clinical trials / multi-armed bandit literature

**Negative**
- Cannot learn complex multi-step policies (correct — that's not our problem)
- Greedy with respect to the binary IC threshold; doesn't optimise tail Sharpe directly

## Alternatives Considered

1. **PPO** — rejected (sample inefficiency, reward hacking)
2. **Manual monthly review only** — rejected at first, but kept as fallback if bandit data is sparse
3. **Multi-armed UCB** — considered; Thompson chosen because of natural Bayesian uncertainty quantification

## References

- `evals/bandit.py` (skeleton)
- Russo et al., *A Tutorial on Thompson Sampling*
- `README.md` D10 (human sign-off requirement)
