#!/bin/bash
# Docker Security Setup for ScrapAI Airflow
# Run this script once after installing Docker

set -e

echo "=== ScrapAI Docker Security Setup ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Check if running as root (bad)
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}ERROR: Do not run this script as root!${NC}"
    echo "Run as your normal user: ./setup-docker-security.sh"
    exit 1
fi

# 2. Check Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: Docker is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}[✓] Docker installed: $(docker --version)${NC}"

# 3. Check if user needs sudo for docker
NEEDS_SUDO=false
if ! docker ps &> /dev/null 2>&1; then
    if sudo docker ps &> /dev/null 2>&1; then
        NEEDS_SUDO=true
        echo -e "${YELLOW}[!] Docker requires sudo (this is actually more secure than docker group)${NC}"
    else
        echo -e "${RED}ERROR: Cannot run docker commands${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}[!] Docker runs without sudo - you're in the docker group${NC}"
    echo "    This is equivalent to root access. Consider rootless Docker for better security."
fi

# 4. Set correct AIRFLOW_UID in .env
CURRENT_UID=$(id -u)
ENV_FILE=".env"

if [ -f "$ENV_FILE" ]; then
    # Update AIRFLOW_UID if it exists, otherwise add it
    if grep -q "^AIRFLOW_UID=" "$ENV_FILE"; then
        sed -i "s/^AIRFLOW_UID=.*/AIRFLOW_UID=$CURRENT_UID/" "$ENV_FILE"
        echo -e "${GREEN}[✓] Updated AIRFLOW_UID to $CURRENT_UID${NC}"
    else
        echo "AIRFLOW_UID=$CURRENT_UID" >> "$ENV_FILE"
        echo -e "${GREEN}[✓] Added AIRFLOW_UID=$CURRENT_UID${NC}"
    fi
else
    echo -e "${RED}ERROR: .env file not found${NC}"
    exit 1
fi

# 5. Generate secure Airflow password
echo ""
echo "=== Airflow Admin Password ==="
CURRENT_PASS=$(grep "^_AIRFLOW_WWW_USER_PASSWORD=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' ')

if [ "$CURRENT_PASS" = "admin123" ] || [ "$CURRENT_PASS" = "admin" ] || [ -z "$CURRENT_PASS" ]; then
    echo -e "${YELLOW}[!] Weak or default password detected${NC}"
    read -p "Generate a secure random password? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        NEW_PASS=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 16)
        sed -i "s/^_AIRFLOW_WWW_USER_PASSWORD=.*/_AIRFLOW_WWW_USER_PASSWORD=$NEW_PASS/" "$ENV_FILE"
        echo -e "${GREEN}[✓] New Airflow password: $NEW_PASS${NC}"
        echo -e "${YELLOW}    Save this password! You'll need it to login at http://localhost:8080${NC}"
    fi
else
    echo -e "${GREEN}[✓] Custom password already set${NC}"
fi

# 6. Check .env file permissions
echo ""
echo "=== Securing .env File ==="
chmod 600 "$ENV_FILE"
echo -e "${GREEN}[✓] Set .env permissions to 600 (owner read/write only)${NC}"

# 7. Create airflow directories with correct permissions
echo ""
echo "=== Setting Up Airflow Directories ==="
mkdir -p airflow/logs airflow/plugins airflow/config
chown -R $CURRENT_UID:$CURRENT_UID airflow/logs airflow/plugins airflow/config 2>/dev/null || true
chmod -R 755 airflow/logs airflow/plugins airflow/config
echo -e "${GREEN}[✓] Airflow directories created with correct permissions${NC}"

# 8. Warn about exposed credentials
echo ""
echo "=== Security Warnings ==="
if grep -q "S3_SECRET_KEY=" "$ENV_FILE" && [ "$(grep 'S3_SECRET_KEY=' "$ENV_FILE" | cut -d'=' -f2)" != "" ]; then
    echo -e "${YELLOW}[!] Your .env contains S3 credentials${NC}"
    echo "    Make sure .env is in .gitignore (never commit secrets!)"
fi

if grep -q ".env" .gitignore 2>/dev/null; then
    echo -e "${GREEN}[✓] .env is in .gitignore${NC}"
else
    echo -e "${RED}[!] WARNING: .env may not be in .gitignore!${NC}"
    read -p "Add .env to .gitignore? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ".env" >> .gitignore
        echo -e "${GREEN}[✓] Added .env to .gitignore${NC}"
    fi
fi

# 9. Summary
echo ""
echo "=== Setup Complete ==="
echo ""
echo "To start Airflow:"
if [ "$NEEDS_SUDO" = true ]; then
    echo "  sudo docker compose -f docker-compose.airflow.yml up -d"
else
    echo "  docker compose -f docker-compose.airflow.yml up -d"
fi
echo ""
echo "Access Airflow at: http://localhost:8080"
echo "Username: admin"
echo "Password: (check your .env file)"
echo ""
echo "To stop Airflow:"
if [ "$NEEDS_SUDO" = true ]; then
    echo "  sudo docker compose -f docker-compose.airflow.yml down"
else
    echo "  docker compose -f docker-compose.airflow.yml down"
fi
