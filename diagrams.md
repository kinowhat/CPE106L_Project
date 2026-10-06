# Circles: Diagrams

These diagrams use [Mermaid](https://mermaid.js.org/), which GitHub renders automatically.
Save this file as `docs/diagrams.md` and link to it from the README.

## 1. Entity-relationship diagram

```mermaid
erDiagram
    USER ||--|| USERPROFILE : "has (related_name=profile)"
    USER ||--o{ MEMBERSHIP : joins
    CIRCLE ||--o{ MEMBERSHIP : "has (related_name=memberships)"
    CIRCLE ||--o{ EVENT : "has (related_name=circle_events)"
    USER |o--o{ EVENT : "owns (user, nullable)"
    USER |o--o{ EVENT : "proposes (proposed_by, SET_NULL)"
    EVENT ||--o{ PROPOSALVOTE : "has (related_name=votes)"
    USER ||--o{ PROPOSALVOTE : casts

    USERPROFILE {
        string timezone "default Asia/Manila"
        image avatar "optional"
        datetime free_until "optional"
    }
    CIRCLE {
        string circle_name "max 32"
        string circle_tag "max 64"
        string invite_code "unique"
        datetime creation_date
    }
    MEMBERSHIP {
        string role "owner or member"
    }
    EVENT {
        string event_name "max 32"
        text event_description
        datetime start_time
        datetime end_time
        string status "personal, pending, approved"
        string poll_type "majority_all, majority_voters, optin"
        datetime proposed_at
    }
    PROPOSALVOTE {
        string choice "yes or no"
        datetime voted_at
    }
```

Unique constraints: `Membership(user, circle)` and `ProposalVote(event, user)`.
A pending poll has `Event.user = NULL`, so it never blocks anyone's calendar.

## 2. Request flow

```mermaid
flowchart LR
    B[Browser] --> RU["Circles/urls.py<br/>(root URLconf)"]
    RU --> AU["CirclesApp/urls.py"]
    AU --> MW["TimezoneMiddleware<br/>(activates user timezone)"]
    MW --> V["views.py"]
    V --> F["forms.py<br/>validate input"]
    V --> M["models.py<br/>read / write DB"]
    V --> P["polls.py<br/>voting rules"]
    V --> C["conflicts.py<br/>overlap checks"]
    V --> T["Template<br/>(extends base.html)"]
    CP["context_processors.py<br/>notifications"] --> T
    TF["circle_extras.py<br/>filters"] --> T
    T --> R[HTML response]
    V -. "redirect / JSON / .ics" .-> R
```

In practice Django runs middleware before URL matching. The diagram orders them by what the
developer thinks about, not by exact execution order.

## 3. Module dependencies

```mermaid
flowchart TD
    S[settings.py] -. registers .-> MWF[middleware.py]
    S -. registers .-> CPF[context_processors.py]
    S -. ROOT_URLCONF .-> RU[Circles/urls.py]
    RU --> AU[CirclesApp/urls.py]
    AU --> V[views.py]
    V --> F[forms.py]
    V --> PO[polls.py]
    V --> CO[conflicts.py]
    V --> MO[models.py]
    F --> MO
    PO --> MO
    CO --> MO
    MWF --> MO
    CPF --> MO
```

`models.py` imports nothing from the app, which avoids circular imports.

## 4. Sequence: voting on a poll

```mermaid
sequenceDiagram
    actor U as Member
    participant T as circle_detail.html (JS)
    participant V as vote_proposal_view
    participant DB as Database
    participant P as polls.py

    U->>T: Click Yes / No
    T->>V: POST /proposals/id/vote/ (AJAX)
    V->>DB: Check membership, event is pending
    V->>DB: update_or_create ProposalVote
    V->>P: poll_is_ready(poll)
    alt condition met
        V->>P: resolve_poll(poll)
        P->>DB: poll becomes approved event (anchor user)
        P->>DB: get_or_create copies for other targets
        V-->>T: JSON resolved=true
        T->>T: reload page
    else not yet
        V-->>T: JSON yes/no/total counts
        T->>T: update progress bars
    end
```

## 5. Poll resolution logic

```mermaid
flowchart TD
    A[Vote saved] --> B{poll_type?}
    B -- optin --> C{"Every member voted<br/>AND at least one Yes?"}
    B -- "majority_all /<br/>majority_voters" --> D{"Yes votes ><br/>50% of ALL members?"}
    C -- no --> W[Stay pending]
    D -- no --> W
    C -- yes --> R[resolve_poll]
    D -- yes --> R
    X["Owner or proposer<br/>clicks Finalize now<br/>(optin only)"] --> R
    R --> TG{"Who are the targets?"}
    TG -- majority_all --> ALL[Every member]
    TG -- "majority_voters / optin" --> YES[Yes voters only]
    ALL --> E{Any targets?}
    YES --> E
    E -- none --> W
    E -- yes --> AN["Anchor = proposer if a target,<br/>else lowest user id"]
    AN --> AP["Poll row: status = approved,<br/>user = anchor"]
    AP --> CP["Other targets: get_or_create<br/>a copy (status = approved)"]
```

## 6. Event status lifecycle

```mermaid
stateDiagram-v2
    [*] --> personal: User adds event to own calendar
    [*] --> pending: Member proposes a poll (user = NULL)
    pending --> approved: Poll resolves
    [*] --> approved: Owner uses Quick Add
    personal --> [*]: Edit or delete
    approved --> [*]: Delete
```

Only `personal` and `approved` events count as busy time in conflict checks and the availability heatmap.
