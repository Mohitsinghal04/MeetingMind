#!/bin/bash
# Test Cloud SQL connection from Cloud Shell

source .env

echo "Testing connection to Cloud SQL..."
echo "DB_HOST: $DB_HOST"
echo "DB_NAME: $DB_NAME"
echo "DB_USER: $DB_USER"
echo ""

# Test with psql
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT version();"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Connection successful!"
else
    echo ""
    echo "❌ Connection failed!"
    echo ""
    echo "Troubleshooting:"
    echo "1. Check if Cloud SQL instance is running:"
    echo "   gcloud sql instances describe meetingmind-db --format='value(state)'"
    echo ""
    echo "2. Check authorized networks:"
    echo "   gcloud sql instances describe meetingmind-db --format='value(settings.ipConfiguration.authorizedNetworks)'"
    echo ""
    echo "3. Try connecting via Cloud SQL Proxy instead:"
    echo "   cloud_sql_proxy -instances=${PROJECT_ID}:${REGION}:meetingmind-db=tcp:5432"
fi
