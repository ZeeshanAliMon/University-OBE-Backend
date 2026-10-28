#!/bin/bash
# Iqra University OBE Backend — setup
# First time: bash setup.sh
# After pulls: python manage.py migrate (only if new migrations exist)

set -e

echo "📦 Installing dependencies..."
pip install -r requirements.txt --break-system-packages -q

echo "🗄️  Running migrations..."
python manage.py migrate


echo ""
echo "🚀 Ready. Start the server with:"
echo "   python manage.py runserver"
