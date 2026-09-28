# MineGuard 1.1.0 upgrade notes

This release is an **in-place upgrade** of the existing `mineguard-final` project. It is not a replacement architecture.

## Main files changed

- `app/page.tsx` — dashboard UX, map, node inspection, modes, demo playback, alert lifecycle, history, network, settings.
- `app/globals.css` — full professional light engineering visual system and responsive layout.
- `lib/demo.ts` — scalable node/zone configuration and richer synthetic observation state.
- `lib/types.ts` — operation modes, layer state, node model outputs and expanded alert lifecycle.
- `app/api/state/route.ts` — parameterized state snapshots.
- `app/api/ingest/route.ts` — clarified hardware integration boundary.
- `app/api/ml/route.ts` — clarified ML adapter boundary.
- `README.md` / `docs/FINAL-VERIFICATION.md` — updated architecture and verification notes.

## Architecture preserved

The dashboard remains a Next.js application with local API routes and a data-driven frontend. The update deliberately avoids introducing a new frontend framework, database requirement, map-provider dependency, or separate operator application.

## Next integration step

Connect the physical gateway and the ML team's actual inference pipeline to the existing API/data-source seams. The dashboard should then consume the same logical node/zone/alert model without a frontend rewrite.
