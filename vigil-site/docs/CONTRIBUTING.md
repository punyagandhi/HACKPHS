# Updating the website

Repository: https://github.com/punyagandhi/HACKPHS
Website source: vigil-site/
Public site: https://hackivisyx.com and https://www.hackivisyx.com

## Local development

```sh
git clone https://github.com/punyagandhi/HACKPHS.git
cd HACKPHS/vigil-site
npm ci
npm run dev
```

## Check and push

Before editing, pull the current repository and follow its existing branch rules. For a shared change, use a branch and pull request:

```sh
git pull --ff-only
git switch -c website/describe-change
# Edit the website files.
npm run lint
npm run typecheck
npm test
npm run build
cd .. # Return from vigil-site/ to the repository root.
git add vigil-site/
git commit -m "Update website: describe the visible change" -m "Explain why, list verification results, and note deployment status."
git push -u origin website/describe-change
```

Open a pull request to main with a short explanation, validation results, and any relevant screenshots. Keep code comments focused on why something works or an important constraint. Never force-push shared main. Keep the Arduino sketch separate from website work.

## Deployment

A GitHub push does not currently deploy the site automatically. Build output is dist/ and works on a static host. The current hosting is ChatGPT Sites, project appgprj_6aca82392bdc8191bf31d40676d825f5. Deploy the tested website through the existing Sites project, preserving public access and custom domains, then verify both URLs and the simulation reset/alerts. Do not change DNS for a routine content update.

Cloudflare manages hackivisyx.com. Both hostnames use HTTPS. Email is intentionally disabled with null MX, deny-all SPF, empty wildcard DKIM, and reject DMARC. Keep these restrictions until email setup is explicitly requested.

## Future updates

For subsequent website work, commit and push the source here with a meaningful summary and check results. State whether the live website was deployed. Do not commit API keys, .env files, node_modules/, dist/, or deployment archives. .env.example is a non-secret template.
