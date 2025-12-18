# Airflow Setup

## Setup

### 1. Configure

Add to `.env`:
```bash
_AIRFLOW_WWW_USER_USERNAME=admin
_AIRFLOW_WWW_USER_PASSWORD=your_password
AIRFLOW_UID=$(id -u)
```

### 2. Start

```bash
docker compose -f docker-compose.airflow.yml up -d
```

Wait ~1 minute for initialization.

### 3. Access

http://localhost:8080

Login with credentials from step 1.

## Usage

All your spiders appear as DAGs. Click to trigger crawls.

Data saves to: `data/{spider_name}/YYYY-MM-DD/crawl_HHMMSS.jsonl`

## Stop

```bash
docker compose -f docker-compose.airflow.yml down
```
