## Description:

Helps agents create, read, edit, search, share, and organize WPS/Kdocs cloud documents, spreadsheets, presentations, and knowledge bases.

This skill is ready for commercial/non-commercial use.

## Publisher:

[kdocs-app](https://clawhub.ai/user/kdocs-app)

### License/Terms of Use:

MIT-0

## Use Case:

People and teams use this skill to have an agent manage WPS/Kdocs cloud files, draft reports, update spreadsheets and presentations, and organize shared knowledge.

### Deployment Geography for Use:

Global

## Known Risks and Mitigations:

Risk: Installing an external CLI requires trusting its distribution channel.

Mitigation: Install only if you trust the Kdocs/WPS CLI distribution channel.

Risk: Account tokens grant access to personal WPS cloud documents.

Mitigation: Prefer browser-based CLI login over pasting tokens into chat.

Risk: Bulk edits, deletions, sharing changes, and webhooks can have unintended effects.

Mitigation: Review proposed actions and explicitly confirm delete, share, and webhook operations before execution.

## Reference(s):

- [Kdocs skill release](https://clawhub.ai/kdocs-app/skills/kdocs-skill)
- [Kdocs cloud documents and account access](https://www.kdocs.cn/latest)
- [WPS 365 CLI documentation](https://github.com/wps365-open/cli)

## Skill Output:

**Output Type(s):** [Text, Markdown, Shell commands, Guidance]

**Output Format:** [Text or Markdown with Kdocs CLI commands and document-editing guidance]

**Output Parameters:** [1D]

**Other Properties Related to Output:** [May trigger changes to the user's WPS cloud documents and sharing settings.]

## Skill Version(s):

2.7.1 (source: ClawHub release metadata)

## Ethical Considerations:

Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment.
