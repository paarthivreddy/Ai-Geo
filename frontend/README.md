# GeoCare AI Frontend

Next.js 14 + TypeScript frontend for the India Patient Address Intelligence Platform.

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **UI Components**: shadcn/ui (Radix UI primitives)
- **Charts**: Apache ECharts (echarts-for-react)
- **State Management**: TanStack Query (React Query)
- **Forms**: React Hook Form + Zod
- **Notifications**: Sonner
- **Icons**: Lucide React

## Getting Started

### Prerequisites

- Node.js 20+
- pnpm (recommended) or npm

### Installation

```bash
cd frontend
cp .env.example .env.local
npm install
```

### Development

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Build

```bash
npm run build
npm start
```

### Linting & Type Checking

```bash
npm run lint
npm run type-check
```

## Project Structure

```
src/
├── app/                    # Next.js App Router pages
│   ├── (auth)/            # Auth layout group (login, register)
│   ├── (dashboard)/       # Dashboard layout group
│   │   ├── upload/        # File upload page
│   │   ├── jobs/          # Job list & detail pages
│   │   ├── reports/       # Quality reports
│   │   └── dashboard/     # Analytics dashboard
│   ├── (admin)/           # Admin layout group
│   ├── layout.tsx         # Root layout
│   ├── page.tsx           # Landing page
│   ├── providers.tsx      # Context providers
│   └── globals.css        # Global styles
├── components/
│   ├── ui/                # shadcn/ui components
│   ├── charts/            # ECharts wrappers
│   ├── forms/             # Form components
│   ├── tables/            # Data table components
│   └── layout/            # Layout components (sidebar, header)
├── hooks/                 # Custom React hooks
├── lib/                   # Utilities & API client
├── types/                 # TypeScript types
└── styles/                # Additional styles
```

## Key Pages

| Route | Description |
|-------|-------------|
| `/` | Landing page |
| `/login` | Authentication |
| `/upload` | File upload & profiling |
| `/jobs` | Job list with filtering |
| `/jobs/[id]` | Job detail with progress |
| `/reports/[id]` | Quality report |
| `/dashboard` | Analytics overview |
| `/dashboard/geography` | Geographic heatmaps |
| `/dashboard/quality` | Quality trends |
| `/admin/users` | User management |
| `/admin/geography` | Geography data refresh |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API base URL | `http://localhost:8000/api/v1` |

## Docker

```bash
# Development
docker compose -f docker-compose.yml up frontend

# Production
docker build -f docker/Dockerfile.frontend -t geocare-frontend .
docker run -p 3000:3000 geocare-frontend
```

## API Integration

The frontend communicates with the FastAPI backend via:
- REST API for CRUD operations
- Server-Sent Events (SSE) for real-time job progress
- File uploads via multipart/form-data

## Deployment

The frontend is deployed as a standalone Next.js application behind nginx, with API requests proxied to the backend.

## License

MIT