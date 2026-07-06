// ─────────────────────────────────────────────────────────────────────────
// Root.tsx — registers the one composition. The video's duration is COMPUTED
// from the phrases passed in (calculateMetadata), so a 2-phrase clip and a
// 4-phrase clip each get exactly the runtime they need — no dead air, no cutoff.
//
// defaultProps are the SYNTHETIC northstar practice (fixtures/northstar-denver):
// these are public marketing tokens, already linted by the engine. Passing
// --props at render time REPLACES them with another practice's approved phrases.
// ─────────────────────────────────────────────────────────────────────────
import React from "react";
import { Composition } from "remotion";
import { SplitFlapHeadline, totalDurationInFrames } from "./SplitFlapHeadline";
import { headlineSchema } from "./schema";

const FPS = 30;

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="SplitFlapHeadline"
      component={SplitFlapHeadline}
      schema={headlineSchema}
      // Square 1080×1080 — the safest single aspect for IG / LinkedIn / FB feeds.
      width={1080}
      height={1080}
      fps={FPS}
      // Placeholder; the real value is derived from props below.
      durationInFrames={300}
      // SYNTHETIC sample — North Star Counseling (fixtures/northstar-denver).
      // No PHI. Every string here is an engine-linted approved token.
      defaultProps={{
        phrases: [
          "Therapy for the overextended.",
          "burnout · anxiety · perfectionism",
          "adults · graduate students · healthcare workers",
        ],
        accentColor: "#5BE3C9",
        practiceName: "North Star Counseling",
        backgroundColor: "#07051C",
      }}
      calculateMetadata={({ props }) => {
        return {
          durationInFrames: totalDurationInFrames(props.phrases, FPS),
        };
      }}
    />
  );
};
