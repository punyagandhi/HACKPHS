# Website update workflow

For future requested changes to this website, update this source in punyagandhi/HACKPHS and push a descriptive commit. Preserve the Arduino sketch and unrelated repository files. Do not leave changes only in a deployed copy.

Run npm run lint, npm run typecheck, npm test, and npm run build before pushing. Include what changed and verification results in the commit description or pull request. Never commit credentials, node_modules, dist, deployment archives, or private environment files.

GitHub pushes do not automatically publish to the live ChatGPT Site. When a live update is requested, deploy the tested build to the existing Sites project, then verify both hackivisyx.com and www.hackivisyx.com. Keep the domain email disabled unless the user explicitly requests email setup.
