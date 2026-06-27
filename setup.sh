#!/bin/bash
# Iqra University OBE Backend — setup
# First time: bash setup.sh
# After pulls: python manage.py migrate (only if new migrations exist)

set -e

echo "📦 Installing dependencies..."
pip install -r requirements.txt --break-system-packages -q

echo "🗄️  Running migrations..."
python manage.py migrate

# Only seed if database is empty (fresh setup)
USERCOUNT=$(python manage.py shell -c "from core.models import User; print(User.objects.count())" 2>/dev/null || echo "0")

if [ "$USERCOUNT" = "0" ]; then
    echo "🌱 Fresh database detected — seeding..."
    python manage.py seed
else
    echo "✅ Database already has data — skipping seed."
    echo "   (Run 'python manage.py seed' manually to reset all data)"
fi

echo ""
echo "🚀 Ready. Start the server with:"
echo "   python manage.py runserver"
