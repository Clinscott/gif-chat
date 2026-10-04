# What the previous experiment measured

The experiments were explicitly shut down before this public packaging work.
No new model benchmarks are run by this repository’s tools or tests.

The strongest completed pilot compared seven paired GIF groups (14 tasks):
one batched request at requested high effort versus two separate requests at
requested medium effort. This changes request shape and effort together.

| Median paired change | Result |
| --- | --- |
| Input tokens | 37.85% fewer |
| Total input + output tokens | 37.46% fewer |
| Completed-turn time | 20.28% faster |
| Reasoning tokens | 28.28% more |

Both arms produced 16/16 useful replies across the full pilot, with 15/16 passing
the stricter core rubric and no candidate-only core losses. The median completion
times in the paired subset were 17.256 seconds batched and 19.369 seconds for
the sum of two serial requests. The median paired percentage is not the ratio
of those medians. Reasoning is included in output tokens, and cached input is
included in input tokens; cache reuse differed substantially between arms.

These are small, correlated pilot observations. They do not establish a general
accuracy rate, a billing/allowance reduction, a requested-versus-observed backend
identity, or installed Codex/Claude UI performance. Batched frame budgets were
task-specific; selecting six frames in this picker does not reproduce that pilot.
The public release retains bounded frame inspection but makes no claim that its
new button or packaging reproduces the pilot’s token or latency improvements.

Later temporal/cache work did not produce a qualified improvement before shutdown.
Raw private responses, account receipts and the large custody archive remain in
the private research repository and are deliberately absent from this release.
