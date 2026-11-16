# Frontend structure

The browser still receives one page from FastAPI, but its HTML is now assembled
from Jinja templates. This keeps shared layout separate from each application
section without adding a JavaScript framework or a frontend build step.

```text
frontend/
├─ templates/
│  ├─ index.html          # Shared document shell
│  ├─ partials/           # Header and navigation
│  └─ sections/           # One HTML file per system area
├─ js/
│  ├─ api.js              # Authenticated browser requests
│  ├─ router.js           # URL parsing and browser history updates
│  ├─ core/               # Shared DOM helpers, application state, theme
│  ├─ views/              # Page-specific controllers
│  └─ main.js             # Startup and controllers not yet extracted
└─ styles.css             # Shared design tokens and component styles
```

## Adding a screen

1. Add the markup under `templates/sections/`.
2. Include it from `templates/index.html`.
3. Put its page-specific controller in `js/views/`.
4. Keep reusable helpers in `js/core/`.

`js/main.js` remains the integration layer during the staged refactor. Data
Explorer, Dashboard, Detail, Data Catalog, Data Quality, and the record editor
within Admin already live in `js/views/`; the image-intake workflow is split
there too. New page work should not add more page-specific logic there; create
a view module instead.
