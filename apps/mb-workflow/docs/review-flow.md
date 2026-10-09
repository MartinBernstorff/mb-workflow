```mermaid
stateDiagram-v2
    direction LR
    state "agent-reviewing" as agent_reviewing
    [*] --> agent_reviewing
    reviewing --> [*]
    agent_reviewing --> reviewing : reviewed
```
