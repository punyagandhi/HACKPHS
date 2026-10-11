# IVISYX

Pilot-focused single-page evidence website and deterministic product simulation.

## Run

Install Node.js 22+, then `npm ci` and `npm run dev`. `npm run build` produces `dist/`; `npm run preview` serves it. Verify with `npm run typecheck`, `npm run lint`, and `npm test`.

## Hosting and a future domain

The deployment is a portable static build with relative assets. A custom hostname can later be connected to the ChatGPT Site, or `dist/` can be uploaded to another static host with the desired domain. No backend or ChatGPT runtime integration is required by the application. Private ChatGPT access is configured by hosting, independently of the application.

## Content and boundaries

Section 2 is preserved in docs/SOURCE_OF_TRUTH.md and content/facts.ts. Source claims are user supplied and have no supplied citations. Product name lives in src/config.ts. The source's cut-off line is rendered as Expression on… as instructed. The checklist is illustrative. Sound is off until enabled. ElevenLabs is a typed disabled stub; no microphone, camera, network voice calls, credentials or real hardware.

## Live website and team updates

Public HTTPS: https://hackivisyx.com and https://www.hackivisyx.com. Source is maintained in `punyagandhi/HACKPHS` under `vigil-site/`. See [contribution and deployment instructions](docs/CONTRIBUTING.md) for checks, commit messages, pushing, and future updates. GitHub pushes do not automatically deploy the live site.
