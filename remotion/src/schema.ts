// ─────────────────────────────────────────────────────────────────────────
// schema.ts — typed props contract for the split-flap headline video.
//
// HONESTY (read this): `phrases` are supplied by the caller and are the ONLY
// text the video can ever display. In Shaula's pipeline those phrases come from
// a practice's ALREADY-LINTED tokens — the same tagline / specialties /
// populations that engine/build_practice.py ran through engine/banned.py
// (G.lint) before the website could ship, and the exact strings the website's
// split-flap hero (templates/private-practice/hero-scramble.js) cycles. This
// composition therefore invents nothing: no hard-coded claims, no stats, no
// testimonials — it only re-spells approved words. scripts/build-props.mjs
// re-runs the banned-language gate over each phrase as a parity check before it
// is allowed into a props file, so a dishonest phrase cannot reach the renderer.
// ─────────────────────────────────────────────────────────────────────────
import { z } from "zod";

// Hex color like #07051C or #5BE3C9 (the brand accent). Constrained so a stray
// value cannot smuggle arbitrary CSS into the render.
const hexColor = z
  .string()
  .regex(/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/, "accentColor must be a hex color, e.g. #5BE3C9");

export const headlineSchema = z.object({
  // The approved, pre-linted phrases to cycle (e.g. tagline → specialties →
  // populations). 1..8 keeps the clip a sane social length; ≥2 makes it move.
  phrases: z
    .array(z.string().min(1))
    .min(1, "at least one approved phrase is required")
    .max(8, "keep it to 8 phrases for a social-length clip"),
  // Brand accent — drives the active-cell glow and the practice-name footer.
  accentColor: hexColor,
  // The practice name shown as a quiet footer plate (also an approved token).
  practiceName: z.string().min(1),
  // Optional second, darker brand color for the board background. Defaults in
  // the composition to a near-black if omitted.
  backgroundColor: hexColor.optional(),
});

export type HeadlineProps = z.infer<typeof headlineSchema>;
