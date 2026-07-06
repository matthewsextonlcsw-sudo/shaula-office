// Remotion render/studio config. See https://www.remotion.dev/docs/config
// Marketing-video project only — no PHI, no network calls at render time.
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
// 1 = lossless; keep the split-flap text crisp at social-feed sizes.
Config.setCrf(18);
