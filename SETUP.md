# 🚀 NexMarket AI — Development Setup Guide

## Current Status
✅ Backend running on `http://localhost:8002`  
✅ Frontend running on `http://localhost:3000`  
✅ All dependencies installed  

## What You Did ✨
1. ✅ Fixed `optimization_service` import issues
2. ✅ Fixed Pydantic v2 protected namespace warnings
3. ✅ Fixed structlog configuration  
4. ✅ Updated frontend API URL from :8000 → :8002
5. ✅ Added favicon.svg
6. ✅ Created .gitignore files for all folders

---

## Prerequisites for Full Operation

### 1. Database Setup (PostgreSQL)

The backend needs PostgreSQL 14+. Follow these steps:

#### On Windows:
```powershell
# Download PostgreSQL from https://www.postgresql.org/download/windows/
# During installation, set password for 'postgres' user

# Connect to PostgreSQL and create database:
psql -U postgres
```

```sql
CREATE USER nexmarket WITH PASSWORD 'nexmarket';
CREATE DATABASE nexmarket_db OWNER nexmarket;
GRANT ALL PRIVILEGES ON DATABASE nexmarket_db TO nexmarket;
```

#### Verify connection:
```bash
psql -U nexmarket -d nexmarket_db -h localhost
```

### 2. Run Database Migrations

```bash
cd backend
alembic upgrade head
```

### 3. Environment Variables

Backend `.env` (R:\Personal\Projects\DL\NexMarket\backend\.env):
```env
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://nexmarket:nexmarket@localhost:5432/nexmarket_db
CORS_ORIGINS=http://localhost:3000
IMAGE_PROVIDER=mock
LLM_PROVIDER=openai
```

Frontend `.env.local` already created with:
```env
NEXT_PUBLIC_API_URL=http://localhost:8002/api/v1
```

---

## Running the Full Stack

### Terminal 1 - Backend
```bash
cd backend
python -m uvicorn app.main:app --port 8002
```

### Terminal 2 - Frontend
```bash
cd frontend
npm run dev
```

### Access Points
- 🌐 **Frontend**: http://localhost:3000
- 📚 **API Docs**: http://localhost:8002/docs
- 💚 **API Health**: http://localhost:8002/health

---

## Troubleshooting

### "ERR_CONNECTION_REFUSED" when creating campaigns
**Solution**: Backend isn't running or database isn't connected
1. Ensure PostgreSQL is running
2. Run `alembic upgrade head` to create tables
3. Restart backend: `python -m uvicorn app.main:app --port 8002`

### "404 Not Found" on favicon
**Solution**: Already fixed! Frontend now has `/public/favicon.svg`
- Clear browser cache (Ctrl+Shift+Delete)
- Hard refresh (Ctrl+Shift+R)

### Hot reload not working
**Solution**: 
- Frontend: Changes auto-reload (Next.js dev mode)
- Backend: Restart server when code changes

### CORS errors
**Solution**: Ensure `CORS_ORIGINS=http://localhost:3000` in backend `.env`

---

## Key Files Changed
- [api.ts](frontend/src/lib/api.ts) — Updated API URL to :8002
- [layout.tsx](frontend/src/app/layout.tsx) — Added favicon config
- [logging.py](backend/app/core/logging.py) — Fixed structlog factory
- [optimizer.py](backend/app/services/optimization/optimizer.py) — Exported `campaign_optimizer`
- [schemas.py](backend/app/schemas/schemas.py) — Fixed Pydantic warnings
- [.gitignore](.gitignore) — Project-wide git excludes
- [.gitignore](backend/.gitignore) — Backend-specific excludes
- [.gitignore](frontend/.gitignore) — Frontend-specific excludes

---

## Next Steps

1. **Set up PostgreSQL** (required for campaigns to persist)
2. **Configure API keys** (optional, for AI features):
   - OpenAI: `OPENAI_API_KEY=sk-...`
   - For mock mode: leave empty (already set)
3. **Test campaign creation**:
   - Navigate to http://localhost:3000
   - Click "New Campaign"
   - Fill in details and submit

---

## Development Tips

### API Testing
```bash
# Test backend health
curl http://localhost:8002/health

# Create campaign (requires DB)
curl -X POST http://localhost:8002/api/v1/campaigns/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test",
    "product_name": "Test Product",
    "description": "Test",
    "offer": "Test",
    "target_audience": "Everyone",
    "campaign_goal": "brand_awareness",
    "preferred_platform": "instagram"
  }'
```

### Debug Frontend
- Open DevTools: F12
- Check Console tab for errors
- Use React DevTools browser extension: https://reactjs.org/link/react-devtools

### Monitor Logs
```bash
# Backend logs show in terminal
# Frontend logs in browser console (F12)
```

---

## Port Reference
| Service | Port | URL |
|---------|------|-----|
| Frontend | 3000 | http://localhost:3000 |
| Backend API | 8002 | http://localhost:8002 |
| PostgreSQL | 5432 | localhost:5432 |
| n8n (optional) | 5678 | http://localhost:5678 |

---

**Last Updated**: 2026-07-23  
**Status**: ✅ Ready for development (pending DB setup)
