### Security Sub-Agent Priority (Phase 0 - MANDATORY CHECK)

Available security specialists: {{agent_names}}

| 用户意图 | 优先委派 | 触发信号 |
|---------|---------|---------|
{{routing_table}}

Routing rules:
- Single IOC or basic reputation lookup: handle directly with tools.
- Multi-IOC, alert context, attribution, correlation, or structured assessment: delegate to the most specific security sub-agent.
- Security specialists are sub-agents: call `delegate_task(subagent_type="...")`, never put their names in `load_skills`.
