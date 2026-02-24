# Layer 1 Setup Guide — React Shell

## What you're building
The complete React skeleton: header with nav tabs, watchlist sidebar,
4 screen placeholders with routing, shared symbol state, favorites
with localStorage persistence, and the new logo.

After these steps you'll have a working app where:
- Clicking a watchlist symbol updates every screen title
- Tabs switch between 4 screens via URL routing
- The Favorites tab shows an empty state (ready for stars)
- The new chart-line logo appears in the header

---

## Step 1: Create the Vite + React project

Your existing `web/` folder may already have a React project from
the Phase 2 setup. If it does, skip to Step 2. If not (or if you
want a clean start):

Open PowerShell in VS Code (Terminal → New Terminal), then:

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"

# Create new Vite project (choose React → JavaScript when prompted)
npm create vite@latest web -- --template react

cd web
npm install

# Add the packages we need
npm install react-router-dom axios
```

**WHY these packages:**
- `react-router-dom` — handles URL-based navigation (each tab is a URL)
- `axios` — HTTP client for talking to your FastAPI backend

---

## Step 2: Clean out the default Vite starter files

Vite creates some example files we don't need. Delete these:

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer\web"

# Remove Vite's example files
Remove-Item src\App.css
Remove-Item src\index.css
Remove-Item src\assets\react.svg -ErrorAction SilentlyContinue
```

---

## Step 3: Copy the Layer 1 files

Download the zip from this chat (or copy file by file). The target
structure inside `options-analyzer/web/src/` should be:

```
src/
├── main.jsx                    ← REPLACE the existing one
├── App.jsx                     ← REPLACE the existing one
│
├── styles/
│   └── global.css              ← NEW — design tokens
│
├── api/
│   └── client.js               ← NEW — API bridge
│
├── assets/
│   └── Logo.jsx                ← NEW — SVG logo component
│
├── context/
│   └── AppContext.jsx           ← NEW — shared state
│
├── components/
│   ├── Layout.jsx + Layout.css
│   ├── Header.jsx + Header.css
│   ├── Watchlist.jsx + Watchlist.css
│   ├── Toast.jsx + Toast.css
│   ├── StarButton.jsx + StarButton.css
│   └── ScoreBar.jsx + ScoreBar.css
│
├── pages/
│   ├── VerticalsPage.jsx
│   ├── LongCallsPage.jsx
│   ├── DirectionalPage.jsx
│   ├── FavoritesPage.jsx + FavoritesPage.css
│   └── PageShared.css
│
└── hooks/                      ← Empty for now, used in Layer 2
```

**HOW to copy in VS Code:**
1. In the Explorer panel (left sidebar), right-click `src/` → "New Folder"
2. Create each subfolder: `styles`, `api`, `assets`, `context`, `components`, `pages`, `hooks`
3. Right-click each folder → "New File" → paste the file contents

Or if you prefer PowerShell, create the folders first:
```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer\web\src"
mkdir styles, api, assets, context, components, pages, hooks
```

---

## Step 4: Verify the HTML entry point

Check that `web/index.html` has a `<div id="root">` — Vite's
default template already does this, but just confirm:

```html
<!-- web/index.html — should already look like this -->
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Options Analyzer</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

You can update the `<title>` to "Options Analyzer" while you're there.

---

## Step 5: Start the dev server

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer\web"
npm run dev
```

Open `http://localhost:5173` in your browser. You should see:

✅ Dark blue background (not white — means global.css loaded)
✅ Cyan "Options Analyzer" logo + text in the header
✅ Four nav tabs: Vertical Spreads, Long Calls, Directional Compare, ★ Favorites
✅ Watchlist sidebar on the left with 6 symbols
✅ "Vertical Spread Analysis — SPY" in the main area
✅ Clicking QQQ in the watchlist changes all titles to QQQ + shows a toast
✅ Clicking ★ Favorites tab shows the empty state
✅ URL changes to /verticals, /long-calls, etc. as you switch tabs

---

## Step 6: Also replace the logo SVG file

If you have a static `logo.svg` file anywhere in `web/public/`,
replace it with the new one from the downloads. But for the React
app, the logo is rendered as a component (`Logo.jsx`), so the SVG
file is just for external use (favicons, social sharing, etc.).

---

## What's next (Layer 2)

Once you confirm Layer 1 is working, we'll build out the analysis
screens one at a time:
1. Vertical Spreads — form + API call + results table + star buttons
2. Long Calls — same pattern
3. Directional Compare — thesis form + strategy table
4. Favorites — wire up the ⟳ refresh to the quote API

Each screen follows the same pattern: form at top, API call on
submit, map results to table rows with <StarButton> components.
