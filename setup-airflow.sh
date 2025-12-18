#!/bin/bash
set -e

echo "🚀 ScrapAI Airflow Setup"
echo "========================"
echo ""

# Check if .env.airflow exists
if [ ! -f .env.airflow ]; then
    echo "❌ .env.airflow not found!"
    echo "Please copy .env.airflow.example and configure it first."
    exit 1
fi

# Check if .env exists or create from .env.airflow
if [ ! -f .env ]; then
    echo "📝 Creating .env from .env.airflow..."
    cp .env.airflow .env
else
    echo "✓ .env file exists"
fi

# Set AIRFLOW_UID if not already set
if ! grep -q "AIRFLOW_UID" .env; then
    echo "📝 Setting AIRFLOW_UID..."
    echo "AIRFLOW_UID=$(id -u)" >> .env
else
    echo "✓ AIRFLOW_UID already set"
fi

# Create necessary directories
echo "📁 Creating Airflow directories..."
mkdir -p airflow/dags airflow/logs airflow/plugins airflow/config
echo "✓ Directories created"

# Fix permissions
echo "🔒 Setting permissions..."
sudo chown -R $(id -u):$(id -g) airflow/ 2>/dev/null || true
chmod -R 755 airflow/
echo "✓ Permissions set"

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Review and edit .env to set your database credentials"
echo "2. Change default Airflow admin password in .env:"
echo "   _AIRFLOW_WWW_USER_PASSWORD=your_secure_password"
echo "3. Start Airflow:"
echo "   docker-compose -f docker-compose.airflow.yml up -d"
echo "4. Access Airflow UI at: http://localhost:8080"
echo "   Username: admin"
echo "   Password: (whatever you set in .env)"
echo ""
echo "📖 For more information, see: airflow/README.md"
