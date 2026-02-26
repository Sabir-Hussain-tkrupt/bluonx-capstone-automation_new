# Frontend — React + Vite + TypeScript + TailwindCSS v4

## Stack Versions

- React 18 with TypeScript
- Vite as build tool
- TailwindCSS v4 (CSS-first config, NOT tailwind.config.js)
- React Router v6 for routing
- React Query for server state / API caching
- Supabase JS client for direct reads (protected by RLS)

## Directory Structure (Feature-Based)

```
frontend/src/
├── features/           # Feature modules (each self-contained)
│   ├── auth/           # Login, registration, password reset
│   ├── dashboard/      # Main dashboard layout and widgets
│   ├── vendors/        # Vendor CRUD, onboarding, contacts
│   ├── projects/       # Project CRUD, document management
│   ├── tasks/          # Task management within projects
│   ├── bids/           # Bid packages, invitations, submissions
│   ├── awards/         # Award decisions, contracts
│   └── milestones/     # Milestone tracking, alerts
├── components/         # Shared/reusable UI components
├── hooks/              # Shared custom hooks
├── lib/                # Utilities, Supabase client, helpers
├── types/              # Shared TypeScript types/interfaces
├── layouts/            # Page layout wrappers
└── routes/             # Route definitions
```

Each feature folder should follow this internal structure:
```
features/vendors/
├── components/         # Feature-specific components
├── hooks/              # Feature-specific hooks
├── types/              # Feature-specific types
├── api/                # Supabase queries and FastAPI calls
└── index.ts            # Public exports
```

## Key Conventions

### Imports
- Use path alias `@/` which maps to `src/`
- Example: `import { Button } from '@/components/Button'`

### Components
- Functional components with TypeScript interfaces for props
- Named exports (not default exports)
- Colocate component-specific styles and types

### TailwindCSS v4
- Config is in `frontend/src/app.css` using `@theme` directive, NOT in a tailwind.config.js
- Use Tailwind utility classes directly, avoid custom CSS when possible

### State Management
- React Query for all server state (Supabase reads, FastAPI calls)
- React context only for auth state and UI state (sidebar open, theme)
- No Redux or Zustand — keep it simple for MVP

### Forms
- React Hook Form for form management
- Zod for schema validation (shared with backend Pydantic where possible)

### Environment Variables
- Vite exposes env vars prefixed with `VITE_`
- Supabase URL: `VITE_SUPABASE_URL`
- Supabase anon key: `VITE_SUPABASE_ANON_KEY`
- Defined in `frontend/.env` (gitignored) with template in `frontend/.env.example`

## Auth Flow

- Supabase Auth handles email/password signup, login, password reset
- On signup, a DB trigger (`fn_handle_new_auth_user`) auto-creates a `public.users` row
- The frontend checks `auth.getSession()` and reads user profile from `public.users`
- Protected routes redirect to `/login` if no session
- Roles (`admin`, `project_manager`) determine UI visibility, not route access for MVP

## Supabase Client Usage

```typescript
// Direct reads (RLS protects data)
const { data } = await supabase.from('vendors').select('*')

// Writes go through FastAPI (do NOT write directly via Supabase client)
await fetch('/api/vendors', { method: 'POST', body: JSON.stringify(vendor) })
```

## Commands

```bash
cd frontend
npm install          # Install dependencies
npm run dev          # Start dev server (Vite)
npm run build        # Production build
npm run lint         # ESLint
npm run preview      # Preview production build
```
