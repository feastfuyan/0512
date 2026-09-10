## Description: <br>
Turn OpenClaw into a learning-loop agent with seeded workspace rules, skill promotion, reflective memory, and proactive maintenance. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[haidiantoutou](https://clawhub.ai/user/haidiantoutou) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
Developers and OpenClaw users use this skill to add a local learning loop that retrieves prior lessons, reflects after significant work, and promotes repeated patterns into stable rules or future skills. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Local memory and seed blocks can shape future agent behavior in ways the user may not expect. <br>
Mitigation: Enable workspace seed blocks only with user consent, keep Hermes additions additive and small, and record paused or excluded repositories in the local Hermes state. <br>
Risk: Stored lessons can become stale, noisy, or too broad for future sessions. <br>
Mitigation: Review ~/hermes-agent/ periodically, keep memory.md short and operational, archive stale lessons, and promote only patterns with repeated evidence. <br>
Risk: Sensitive information could be written into local memory if users or agents record it. <br>
Mitigation: Store only operational lessons and workflow decisions; do not store credentials, secrets, payment data, health data, or copied transcripts. <br>


## Reference(s): <br>
- [ClawHub skill page](https://clawhub.ai/haidiantoutou/skills/hermes-agent) <br>
- [Hermes Agent homepage](https://clawic.com/skills/hermes-agent) <br>
- [Setup guide](setup.md) <br>
- [Memory template](memory-template.md) <br>
- [OpenClaw seed blocks](openclaw-seed.md) <br>
- [Loop design](loop.md) <br>
- [Promotion rules](promotion.md) <br>


## Skill Output: <br>
**Output Type(s):** [Guidance, Markdown, Shell commands, Configuration] <br>
**Output Format:** [Markdown instructions with shell command snippets and configuration templates] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Produces local-memory and workspace-seed guidance for agent behavior; no API output is defined.] <br>

## Skill Version(s): <br>
1.0.0 (source: frontmatter and server release evidence) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
