# BluOnX Capstone Automation

Bid Management & Vendor Coordination System for BluOnX Development and Capstone LLC.

## Project Structure
```
bluonx-capstone-automation/
├── frontend/          # React + Vite + TypeScript + TailwindCSS
├── backend/           # FastAPI + Python (Phase 2)
├── supabase/          # Database migrations & config
├── docs/              # Project documentation
└── .github/workflows/ # CI/CD pipelines
```

## Quick Start

### Prerequisites

- Node.js v18+
- Docker Desktop (for backend, Phase 2+)
- Supabase CLI (`npm install -g supabase`)

### Frontend
```bash
cd frontend
cp .env.example .env          # Fill in your Supabase credentials
npm install
npm run dev                    # → http://localhost:5173
```

### Database
```bash
npx supabase login
npx supabase link --project-ref YOUR_PROJECT_REF
npx supabase db push           # Apply migrations
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite + TypeScript + TailwindCSS |
| Backend | FastAPI + Python (Phase 2) |
| Database | Supabase (PostgreSQL) |
| Hosting | Vercel (frontend) + AWS (backend) |

## Team

- Awais Anwer (Tkrupt)