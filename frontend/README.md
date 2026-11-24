# Frontend structure

The browser still receives one page from FastAPI, but its HTML is now assembled
from Jinja templates. This keeps shared layout separate from each application
section without adding a JavaScript framework or a frontend build step.

```text
frontend/
├─ templates/
│  ├─ index.html          # Shared document shell; loads the stylesheets in order
│  ├─ partials/           # Header and navigation
│  └─ sections/           # One HTML file per system area
├─ js/
│  ├─ api.js              # getJson, adminFetch, uploadForm, fetchAdminSession
│  ├─ router.js           # URL parsing and browser history updates
│  ├─ core/               # Shared DOM helpers, application state, theme
│  ├─ views/              # One controller per page (admin page split by panel)
│  └─ main.js             # Creates the controllers, wires them, routes pages
└─ css/
   ├─ base.css            # Theme colours, layout, type, forms, buttons, tables, metrics
   └─ <page>.css          # explorer, dashboard, catalog, admin, detail, quality
```

## Adding a screen

1. Add the markup under `templates/sections/`.
2. Include it from `templates/index.html`.
3. Put its page-specific controller in `js/views/` and create it in `js/main.js`.
4. Put its styles in `css/<page>.css` and add the `<link>` to `templates/index.html`.
5. Keep reusable helpers in `js/core/` and shared styles in `css/base.css`.

## Stylesheet order

`index.html` loads `base.css` first and then one file per page. When two rules
with the same specificity style the same element, the one loaded later wins, so
a page file can override `base.css` but not the other way round. A rule used by
more than one page belongs in `base.css`. Each page file keeps its own narrow
screen rules (`@media (max-width: 800px)`) at its end.
