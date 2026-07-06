---
name: remotion-video
description: "Make marketing/social videos programmatically with Remotion (videos as React code). Use when the practice wants a video from a script or brief. Public marketing content only — never client/PHI."
version: 1.0.0
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [video, remotion, marketing, content, social]
    related_skills: [blog-scaffolder, website-builder, supertonic]
---

# Remotion Video (Shaula content skill)

Make short marketing/social videos for the practice — programmatically, with **Remotion** (videos as
React components: code in, MP4 out). This skill is the *instructions*; the practitioner installs Remotion
**themselves** (see Setup). We ship no Remotion code, so there's no licensing entanglement for us.

## When to use
The practice wants a video — a service explainer, a social clip, an animated quote card. **Public
marketing content only. Never put client information or PHI in a video.**

## Setup (one time — the practitioner installs Remotion under their own license)
Remotion is **free for individuals and small practices**; a company license applies to larger for-profit
orgs — that's the practitioner's call, not ours.
- **Repo:** https://github.com/remotion-dev/remotion · **Docs:** https://remotion.dev
- Scaffold in the workspace: `npx create-video@latest`

## How to make a video
1. Take the brief (topic, key message, length, brand colors/logo). The **honesty engine applies** — no
   invented stats, claims, or testimonials, exactly like published copy.
2. Write/modify the Remotion composition (`React` + `@remotion/*`) — text, transitions, the practice's
   palette + logo; optional narration via the `supertonic` voice skill.
3. Preview: `npx remotion studio`. Render: `npx remotion render <Composition> out/video.mp4`.
4. The MP4 lands in the workflow box's workspace.

## Guardrails
- **Public marketing only — no PHI, ever.**
- **No fabricated claims** — the honesty rules apply to video copy too.
- **Don't auto-publish.** Rendering is fine; posting/publishing needs the practitioner's approval.
