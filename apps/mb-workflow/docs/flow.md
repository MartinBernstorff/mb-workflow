```mermaid
stateDiagram-v2
    direction LR
    state "grill" as grilling
    state "to-ticket" as speccing
    [*] --> grilling
    merged --> [*]
    grilling --> grilling : grill
    grilling --> speccing : to-ticket
    speccing --> todo : todo
    todo --> implementing : implement
    implementing --> grilling : grill
    implementing --> speccing : to-ticket
    implementing --> qa : qa
    qa --> implementing : implement
    qa --> review : ready
    qa --> merging : merge
    qa --> implementing : resolve-review
    review --> qa : qa
    review --> merging : merge
    review --> merged : merged
    review --> implementing : resolve-review
    merging --> qa : qa
    merging --> merged : merged
```
