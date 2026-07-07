# Portugal Observatory (Observatório Portugal)

An interactive, client-side web application for visualizing electoral results in Portugal from 1975 to 2026. This platform displays highly granular electoral maps and data, down to the level of civil parishes (*freguesias*).

## Features

- **Four Types of Elections:**
  - **Assembly of the Republic** (*Assembleia da República* - Legislative)
  - **Presidential** (*Presidenciais*)
  - **European Parliament** (*Europeias*)
  - **Local/Municipal** (*Autárquicas*), including:
    - Municipal Chamber (*Câmara Municipal* - CM)
    - Municipal Assembly (*Assembleia Municipal* - AM)
    - Parish Assembly (*Assembleia de Freguesia* - AF)
- **High Granularity Map Views:** Visualize results at the **District/Círculo**, **Municipality** (*Concelho*), and **Civil Parish** (*Freguesia*) levels.
- **Dynamic Dashboards:** Detailed sidebar panels showing vote distributions, seat allocation (using the *d'Hondt method*), party rankings, majorities, and voter turnout.
- **Interactive Visualization Modes:** Toggle between "Winner" mode (color by winning party/candidate) and "Performance" mode (color intensity by party share in each territory).
- **Dark Mode Support:** Clean, modern dark-themed user interface designed for high-contrast data visualization.

## Project Structure

- `index.html` — The main entry point and user interface.
- `landing.css` / `style.css` — Modern styling and layout definitions.
- `js/` — Client-side logic:
  - `globals.js` — Global configurations, colors, and election definitions.
  - `cache.js` — IndexedDB/Local storage caching for loaded data files.
  - `maplibre-compat.js` — MapLibre GL helper integrations.
  - `pt/` — Portugal-specific map rendering, UI controls, and result panel rendering.
- `dados/` — Processed output data (GeoJSON maps and JSON election results), dynamically loaded by the client.
- `etl/` — Python scripts to clean, align, and process raw electoral shapefiles and official Excel spreadsheets into optimized JSON/GeoJSON formats.
