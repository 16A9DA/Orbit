# Dashboard

## Overview

Local first personal command center. Monitors infrastructure, cloud services, dev activity, tasks, alerts. Bundled AI assistant. Runs local, opens browser auto. NOC style glassmorphism UI per `DESIGN.md`.

## Architecture

Backend: Django, Django REST Framework, SQLite (dev), PostgreSQL (later). Background scheduler polls integrations.

Integrations: GitHub, Render, Google Cloud, SendGrid, Notion. Notifications via Discord webhook plus in app.

Frontend: single page served by Django, styled per `DESIGN.md`.

## Install

```
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in keys
python manage.py migrate
```

## Usage

Start server. Browser opens auto at `http://127.0.0.1:8000`.

```
dashboard
```

Or:

```
python manage.py runserver
```

## Configuration

All secrets live in `.env`. Never commit. See `.env.example` for keys. No key present means that integration serves mock data.

## Security

Keys read from `.env` only. Stored tokens encrypted at rest. All data stays local. User owns everything.
