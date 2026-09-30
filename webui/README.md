# Operating Swarm Web UI

This directory contains the React-based frontend for Operating Swarm, built with:

- **Vite** - Fast build tool
- **React** - UI framework
- **TypeScript** - Type-safe JavaScript
- **Tailwind CSS** - Utility-first CSS framework
- **DaisyUI** - Component library for Tailwind
- **React Router** - Client-side routing

## Development

### Prerequisites

- Node.js v22+ (recommended)
- npm (comes with Node.js)

### Setup

```bash
# Install dependencies
cd webui/frontend
npm install

# Start development server
npm run dev
```

The development server runs on port 3000 and proxies API requests to the Django backend on port 8000.

### Building for Production

```bash
# Preferred (from repo root) — ADR-001 SPA after pull
make frontend

# Or the underlying script / direct Vite build
./scripts/build_frontend.sh
# cd webui/frontend && npm ci && npm run build
```

Built assets will be in `webui/frontend/dist/` and automatically served by Django.

## Project Structure

```
webui/
└── frontend/
    ├── public/          # Static assets
    ├── src/             # Source code
    │   ├── App.tsx       # Main application
    │   ├── main.tsx      # Entry point
    │   └── index.css     # Global styles
    ├── vite.config.ts   # Vite configuration
    ├── tailwind.config.js # Tailwind config
    └── package.json     # Dependencies
```

## Features

- **Responsive Design**: Works on mobile and desktop
- **Dark/Light Mode**: Toggle between themes
- **SPA Routing**: React Router — **only** `/` (dashboard) and `/chat` (ADR-001)
- **Modern UI**: DaisyUI v5 components
- **API Integration**: Proxied to Django backend

Operator chrome (Teams, Blueprint Library, Settings, Sessions, Agent Creator)
lives on Django trailing-slash routes. Leftover SPA operator pages were deleted
per ADR-001 and must not be remounted.

## Integration with Django

The frontend is automatically detected and served by Django when built
(`webui/frontend/dist/` is gitignored). After pulling SPA changes (ADR-001
route cut, chat auth messaging, mobile dock, etc.), run **`make frontend`**
(or `./scripts/build_frontend.sh`) so journey captures and `/` serve the new
bundle — **rebuild is required** for the `/` + `/chat`-only shell.
The `index` view in `src/swarm/views/web_views.py` prefers built assets over
Django templates when `dist/` exists.

## DaisyUI Components

This project uses DaisyUI v5 with two chrome themes:
- `dark` (default in the SPA — near-black, muted greys, small steel accents)
- `light`

Rainbow / cupcake category colours are intentionally not used on the dashboard.

All DaisyUI components are available for use in the React components.
