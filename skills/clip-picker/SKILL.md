---
name: clip-picker
description: "Select the strongest 60-second moment from a transcript or outline for a social media Reel hook — outputs clip start/end markers and a caption. No video processing. Human records and edits the actual clip."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [social, reels, video, content, marketing]
    related_skills: [ad-creative-engine, newsletter-engine]
---

# Clip Picker (Shaula)

Identifies the single strongest 60-second window in a transcript, talk outline, or podcast
episode for use as a social Reel hook. Outputs only text: the clip's start cue, end cue, a
one-sentence reason it works, and a platform-native caption. No video is generated or processed
— a human records, trims, and posts the clip.

## When to use

The clinician has a recorded talk, workshop, supervision session (non-PHI, business content only),
or podcast appearance and wants to know which moment to clip for Instagram or TikTok.

**Hard scope limit:** transcripts must be business or educational content — workshop teaching,
a podcast interview, a webinar presentation. Never session content, never a client's words, never
any PHI. If the transcript contains anything that could identify a client, stop immediately and
flag to the clinician without processing further.

## How to run

Provide the marketer staff with the transcript or outline and this instruction:

```
Using the clip-picker skill:
1. Read the transcript.
2. If any content could be PHI or identifies a client, STOP and flag — do not continue.
3. Find the single 60-second window that (a) delivers a complete idea, (b) starts on a strong
   hook line, and (c) ends on a payoff or clear takeaway.
4. Output:
   - START CUE: the first sentence of the clip (verbatim)
   - END CUE: the last sentence of the clip (verbatim)
   - REASON: one honest sentence on why this moment works
   - CAPTION (Instagram/TikTok, under 150 characters): sell the idea, not a clinical promise;
     never make the viewer's situation the punchline
5. Do not pick a moment that makes an outcome claim or cites a statistic you cannot verify.
```

## Output format

```
START CUE:  "[verbatim first sentence]"
END CUE:    "[verbatim last sentence]"
REASON:     [why this window — one sentence, honest]
CAPTION:    [under 150 chars — sells the idea, no outcome promise, no condition as punchline]
```

## Honesty contract

The caption follows the same rules as all Shaula marketing output: no outcome promise, no
statistic without a source, no condition as a hook or a punchline. The clip is chosen for
genuine value, not for emotional shock.
