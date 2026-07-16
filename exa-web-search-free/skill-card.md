## Description: <br>
Provides free Exa MCP web, code-context, and company research search tools without requiring an API key. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[whiteknight07](https://clawhub.ai/user/whiteknight07) <br>

### License/Terms of Use: <br>


## Use Case: <br>
Developers, researchers, and agents use this skill to search current web information, retrieve code and documentation examples, and research companies through Exa MCP. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Search terms and optional research inputs are sent to Exa's external service. <br>
Mitigation: Avoid submitting secrets, private code, internal-only URLs, confidential business information, credentials, regulated data, or sensitive personal information. <br>
Risk: People-search and crawling features can retrieve sensitive or policy-relevant web content when enabled. <br>
Mitigation: Use those optional tools only with a legitimate, policy-compliant purpose and review retrieved content before relying on it. <br>


## Reference(s): <br>
- [Exa Search Examples](references/examples.md) <br>
- [Exa MCP Server GitHub Repository](https://github.com/exa-labs/exa-mcp-server) <br>
- [Exa MCP Server npm Package](https://www.npmjs.com/package/exa-mcp-server) <br>
- [Exa Documentation](https://exa.ai/docs) <br>


## Skill Output: <br>
**Output Type(s):** [text, shell commands, configuration, guidance] <br>
**Output Format:** [Markdown with inline bash command examples] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Requires the mcporter command-line tool and sends search or research inputs to Exa's external service.] <br>

## Skill Version(s): <br>
1.0.1 (source: server release evidence) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
