// ─────────────────────────────────────────────────────────────────────────
// SplitFlapHeadline.tsx — a kinetic "Solari" / Penn-Station split-flap board,
// rendered as video. It is the social/marketing twin of the website's hero
// (templates/private-practice/hero-scramble.js): the same calm, legible flap —
// letters step in alphabetical order to land on the next approved phrase, in a
// left→right wave, dimmed while flipping (never a colour strobe).
//
// HONESTY: every glyph drawn comes from `phrases`, which the caller supplies
// from a practice's already-linted tokens (see src/schema.ts). This file holds
// ZERO marketing copy of its own — no claims, no numbers, no testimonials. It
// only re-spells words it is handed.
//
// DETERMINISM: Remotion renders frame N independently and in parallel, so the
// board is a pure function of the frame number — no Math.random, no timers, no
// DOM. The same props always produce the same frames (reproducible renders).
// ─────────────────────────────────────────────────────────────────────────
import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
} from "remotion";
import type { HeadlineProps } from "./schema";

// The flap alphabet — flips advance forward through THIS ring to land on a
// target, exactly like the website board's `glyphs`. Space is index 0 so a
// shrinking line settles trailing cells to blank.
const GLYPHS = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,&·'-";
const GI = (ch: string): number => {
  const i = GLYPHS.indexOf(ch);
  return i; // -1 ⇒ unknown char, rendered static
};

// ── timing (frames). Mirrors hero-scramble.js cadence, expressed per-frame. ──
const FLIP_FRAMES_PER_GLYPH = 2; // frames each cell holds one intermediate glyph
const FLIPS = 7; // glyphs a changing cell steps through before it lands (bounded = calm)
const STAGGER_FRAMES = 2.2; // per-column delay → tight left→right sweep
const HOLD_SECONDS = 2.0; // pause on each fully-spelled phrase
const SETTLE_PAD_FRAMES = 8; // breathing room after the last cell lands

// Per-phrase frame budget = the stagger across all cells + the flip run + hold.
function phraseFrames(text: string, fps: number): number {
  const cols = Math.max(text.length, 1);
  const flipSpan = Math.ceil((cols - 1) * STAGGER_FRAMES) + FLIPS * FLIP_FRAMES_PER_GLYPH;
  return flipSpan + SETTLE_PAD_FRAMES + Math.round(HOLD_SECONDS * fps);
}

// Public so Root.tsx's calculateMetadata can size the composition to the props.
export function totalDurationInFrames(phrases: string[], fps: number): number {
  const list = phrases.length ? phrases : [" "];
  return list.reduce((sum, p) => sum + phraseFrames(p.toUpperCase(), fps), 0);
}

// What glyph is cell `col` showing at `localFrame` of a transition from
// `fromChar` → `toChar`? Returns the glyph plus whether it is mid-flip (dimmed).
function cellGlyph(
  fromChar: string,
  toChar: string,
  col: number,
  localFrame: number
): { ch: string; flipping: boolean } {
  const target = GI(toChar);
  if (target < 0) return { ch: toChar, flipping: false }; // unknown ⇒ static

  const start = GI(fromChar) >= 0 ? GI(fromChar) : 0;
  if (start === target) return { ch: GLYPHS[target], flipping: false }; // unchanged

  const begin = Math.floor(col * STAGGER_FRAMES);
  const elapsed = localFrame - begin;
  if (elapsed < 0) return { ch: GLYPHS[start], flipping: false }; // not our turn yet — hold prior

  const stepsDone = Math.floor(elapsed / FLIP_FRAMES_PER_GLYPH);
  if (stepsDone >= FLIPS) return { ch: GLYPHS[target], flipping: false }; // landed

  // Advance forward through the ring so the FINAL step lands exactly on target
  // (alphabetical, board-like — same as the website's startIdx math).
  const stepsLeft = FLIPS - stepsDone;
  const idx = ((target - stepsLeft) % GLYPHS.length + GLYPHS.length) % GLYPHS.length;
  return { ch: GLYPHS[idx], flipping: true };
}

// One split-flap cell. A thin seam line across the middle sells the "flap".
const Cell: React.FC<{ ch: string; flipping: boolean; accent: string }> = ({
  ch,
  flipping,
  accent,
}) => {
  return (
    <span
      style={{
        position: "relative",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: "0.72em",
        height: "1.06em",
        margin: "0 0.035em",
        borderRadius: "0.07em",
        background: flipping
          ? "linear-gradient(#15151d, #050507)"
          : "linear-gradient(#1d1d27, #0a0a0f)",
        boxShadow: flipping
          ? `inset 0 0 0 1px rgba(255,255,255,0.04)`
          : `inset 0 0 0 1px rgba(255,255,255,0.06), 0 0 14px ${accent}22`,
        color: flipping ? "rgba(255,255,255,0.5)" : "#f3f3f6",
        transition: "none",
      }}
    >
      {/* center seam — the physical flap split */}
      <span
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: "50%",
          height: 1,
          background: "rgba(0,0,0,0.55)",
        }}
      />
      {/* a hairline accent underglow only on a settled cell */}
      {!flipping && (
        <span
          style={{
            position: "absolute",
            left: "12%",
            right: "12%",
            bottom: "0.12em",
            height: 2,
            borderRadius: 2,
            background: accent,
            opacity: 0.55,
            filter: `drop-shadow(0 0 6px ${accent})`,
          }}
        />
      )}
      <span style={{ position: "relative", zIndex: 1 }}>{ch === " " ? " " : ch}</span>
    </span>
  );
};

export const SplitFlapHeadline: React.FC<HeadlineProps> = ({
  phrases,
  accentColor,
  practiceName,
  backgroundColor,
}) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();

  const upper = (phrases.length ? phrases : [" "]).map((p) => p.toUpperCase());

  // Locate which phrase we are on and the local frame within its segment.
  let acc = 0;
  let phraseIndex = 0;
  for (let i = 0; i < upper.length; i++) {
    const len = phraseFrames(upper[i], fps);
    if (frame < acc + len || i === upper.length - 1) {
      phraseIndex = i;
      break;
    }
    acc += len;
  }
  const localFrame = frame - acc;

  // The board flips FROM the previous phrase TO the current one (the first
  // phrase flips up from blank — matches the website settling in from space).
  const toText = upper[phraseIndex];
  const fromText = phraseIndex === 0 ? "" : upper[phraseIndex - 1];
  const cols = Math.max(toText.length, fromText.length);

  // Responsive board size: shrink the cell font so the LONGEST phrase in the
  // whole clip fits the frame width with margin (sizing on the longest phrase,
  // not just the current one, keeps the board a constant size as phrases swap —
  // no jarring resize between lines). Font is expressed in px (deterministic).
  const BOARD_PAD_PX = 56; // visual breathing room each side, inside the frame
  const availWidth = width - BOARD_PAD_PX * 2;
  const perCellEm = 0.72 + 0.07; // cell content width + horizontal margins, in em
  const longestCols = upper.reduce((m, p) => Math.max(m, p.length), 1);
  const maxFontByWidth = availWidth / (longestCols * perCellEm);
  const fontSize = Math.min(104, Math.max(18, maxFontByWidth));

  // Quiet entrance: the whole board eases up + in over the first ~16 frames.
  const intro = interpolate(frame, [0, 16], [0, 1], {
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  const bg = backgroundColor ?? "#07051C";

  const cells: React.ReactNode[] = [];
  for (let c = 0; c < cols; c++) {
    const toCh = c < toText.length ? toText[c] : " ";
    const fromCh = c < fromText.length ? fromText[c] : " ";
    const { ch, flipping } = cellGlyph(fromCh, toCh, c, localFrame);
    cells.push(<Cell key={c} ch={ch} flipping={flipping} accent={accentColor} />);
  }

  return (
    <AbsoluteFill
      style={{
        // a deep brand-dark field with a faint accent vignette
        background: `radial-gradient(120% 120% at 50% 38%, ${accentColor}14 0%, ${bg} 58%, #020205 100%)`,
        fontFamily:
          "'Anton', 'Oswald', 'Arial Narrow', 'Helvetica Neue', Helvetica, Arial, sans-serif",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div
        style={{
          transform: `translateY(${(1 - intro) * 26}px)`,
          opacity: intro,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "0.9em",
        }}
      >
        {/* the board */}
        <div
          style={{
            display: "flex",
            flexWrap: "nowrap",
            alignItems: "center",
            justifyContent: "center",
            fontSize,
            lineHeight: 1,
            letterSpacing: "0.012em",
            fontWeight: 400,
          }}
        >
          {cells}
        </div>

        {/* quiet practice-name plate — an approved token, not a claim */}
        <div
          style={{
            marginTop: "0.4em",
            fontSize: Math.max(15, fontSize * 0.2),
            letterSpacing: "0.34em",
            textTransform: "uppercase",
            color: "rgba(243,243,246,0.7)",
            borderTop: `1px solid ${accentColor}55`,
            paddingTop: "0.55em",
            fontFamily: "'Helvetica Neue', Helvetica, Arial, sans-serif",
            fontWeight: 600,
          }}
        >
          {practiceName}
        </div>
      </div>
    </AbsoluteFill>
  );
};
