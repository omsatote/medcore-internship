# MedCore HMS

MedCore is a dependency-free hospital management system with a browser dashboard,
SQLite persistence, and a simple login page.

## Run locally

```powershell
python index.py
```

Open <http://127.0.0.1:8765>.

Demo login:

- Email: `admin@medcore.com`
- Password: `medcore123`

The local database is created as `medcore.db` and is intentionally ignored by
Git because it contains application data.

## Deployment note

The current application uses Python's built-in threaded HTTP server and local
SQLite storage. It runs locally as documented above. Before deploying to Vercel,
the HTTP entry point and persistence layer should be adapted to Vercel
serverless functions and a hosted database, respectively.
