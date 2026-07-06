---
name: meeting-notes
description: "Summarize business meetings (referral partner calls, supervision, team check-ins) into action-item notes. No PHI, no session content. Stops and flags if clinical content appears."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [notes, admin, meetings, business, no-phi]
    related_skills: [proposal-engine]
---

# Meeting Notes (Shaula)

Produces a clean action-item summary from a business meeting transcript or recording notes.
Intended for administrative and professional meetings: referral partner calls, supervision
check-ins, team stand-ups, vendor calls, workshop planning. This skill is **not** a session
note tool — that is the scribe's job and is PHI-gated. This skill handles business operations
only.

## When to use

The clinician or practice manager wants a written record of a non-clinical business meeting
with follow-up actions captured. No client names, no session content, no PHI.

**Hard scope limit:** if the transcript contains any client name, client presenting concern,
diagnosis, medication, or any other PHI — stop immediately, flag to the clinician, and produce
no output. Business meetings only.

## How to run

Provide the relevant staff member (orchestrator or marketer) with the transcript or notes and
this instruction:

```
Using the meeting-notes skill:
1. Read the transcript.
2. If any content could identify a client or contains PHI (client name, diagnosis, session
   content, medication), STOP immediately and flag to the clinician — produce no summary.
3. Produce a meeting summary in this format:

   MEETING: [name or topic]
   DATE:    [if known]
   WHO:     [attendees by role, not necessarily by name if not relevant]

   KEY DECISIONS
   - [decision 1]
   - [decision 2]

   ACTION ITEMS
   - [ ] [person/role responsible]: [what, by when if stated]
   - [ ] ...

   OPEN QUESTIONS
   - [anything unresolved that needs a follow-up]

4. Keep each item factual and brief. Do not interpret intent or add context not stated in
   the meeting. Flag any item that was ambiguous as [CLARIFY].
```

## Honesty contract

Notes capture what was said and decided — not what the note-taker thinks was meant. Ambiguous
items are flagged [CLARIFY], not resolved by inference. No clinical content ever appears here.
