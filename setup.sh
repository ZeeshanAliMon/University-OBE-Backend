#!/bin/bash
# Iqra University OBE Backend — one command setup
# Usage: bash setup.sh

set -e

echo "📦 Installing dependencies..."
pip install -r requirements.txt --break-system-packages -q

echo "🗄️  Running migrations..."
python manage.py migrate

echo "🌱 Seeding database..."
python manage.py seed

echo ""
echo "✅ Done. Run the server with:"
echo "   python manage.py runserver"
