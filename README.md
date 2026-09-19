# Dashboard

## Overview

Orbit is a local first personal command center. It monitors infrastructure, cloud services, dev activity, tasks, and alerts, and includes a bundled AI assistant. It runs locally and opens your browser automatically. The interface follows a NOC style glassmorphism design documented in `DESIGN.md`.

## Demo

[![Orbit demo video]](brag.mp4)

## Architecture

The backend uses Django and Django REST Framework, with SQLite for development and PostgreSQL planned for later. A background scheduler polls each integration.

Supported integrations include GitHub, Render, Google Cloud, SendGrid, and Notion. Notifications are delivered through a Discord webhook and shown in the app itself.

The frontend is a single page served by Django, styled according to `DESIGN.md`.

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

Start the server. Your browser opens automatically at `http://127.0.0.1:8000`.

```
dashboard
```

Or run it directly:

```
python manage.py runserver
```

## Configuration

All secrets live in `.env`, which should never be committed. See `.env.example` for the full list of keys. If a key is missing, that integration falls back to mock data.

## Security

Keys are read from `.env` only, and stored tokens are encrypted at rest. All data stays local, and you own it.
