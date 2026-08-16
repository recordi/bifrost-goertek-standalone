# BIFROST UI baseline v3.2.1

This directory preserves the locally finalized standalone UI baseline for review and integration into the BIFROST web application.

It is intentionally kept separate from `apps/web` so this branch does not replace the existing application. The team can review this baseline first, then port the approved pieces into the Next/pnpm app.

## Contents

- `index.html` — standalone entry point
- `src/` — React UI source
- `styles.css` — visual styles
- `routes.json` — route manifest
- `src/data.jsx` — self-contained mock data used by the baseline

## Review

Open `index.html` in the project’s existing preview workflow. The baseline uses the same finalized UI package that was agreed on locally; it is not wired into the monorepo build by this change.
