# Airflow Setup for ScrapAI

This directory contains Airflow configuration for managing and monitoring your ScrapAI spiders.

## Quick Start

### 1. Initial Setup

```bash
# Copy environment template and configure
cp .env.airflow .env

# Edit .env and set your database credentials
# Make sure DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD match your ScrapAI database

# Set Airflow UID (run this command to get your user ID)
echo "AIRFLOW_UID=$(id -u)" >> .env

# Change default admin password in .env
# _AIRFLOW_WWW_USER_USERNAME=admin
# _AIRFLOW_WWW_USER_PASSWORD=your_secure_password
```

### 2. Start Airflow

```bash
# Start all Airflow services
docker-compose -f docker-compose.airflow.yml up -d

# Check logs
docker-compose -f docker-compose.airflow.yml logs -f

# Wait for initialization (takes 1-2 minutes)
```

### 3. Access Airflow UI

Open your browser and go to: **http://localhost:8080**

- Username: `admin` (or what you set in .env)
- Password: `admin123` (or what you set in .env)

### 4. Verify Spider DAGs

In the Airflow UI:
1. You should see DAGs for each spider in your database
2. DAG names follow the pattern: `{project}_{spider_name}`
3. Each DAG has tags: `scrapai`, `project:{project_name}`, `spider`

## Features

### Automatic DAG Generation

- **Auto-Discovery**: DAGs are automatically generated from your ScrapAI spider database
- **Project Organization**: Each spider is tagged with its project for filtering
- **Refresh**: DAGs update when Airflow scheduler refreshes (every few minutes)

### Project-Based Organization

**Filtering by Project:**
1. Go to Airflow UI → DAGs page
2. Use tag filter: Click on `project:your_project_name` tag
3. You'll see only spiders for that project

**DAG Naming:**
- Pattern: `{project}_{spider_name}`
- Example: `climate_team_climate_news`
- Default project: `default` (if spider has no project)

### Manual Triggering

**Trigger a spider crawl:**
1. Go to DAGs page in Airflow UI
2. Find your spider DAG
3. Click the "Play" button (▶) to trigger
4. Monitor progress in real-time

**Via CLI:**
```bash
# Trigger a specific spider
docker-compose -f docker-compose.airflow.yml exec airflow-webserver \
  airflow dags trigger {project}_{spider_name}

# Example
docker-compose -f docker-compose.airflow.yml exec airflow-webserver \
  airflow dags trigger default_climate_news
```

### Scheduling Spiders

To add scheduling to spiders, you need to add a `schedule_interval` field to your Spider model.

**Option 1: Add via migration**
```sql
-- Add schedule_interval column to spiders table
ALTER TABLE spiders ADD COLUMN schedule_interval VARCHAR(50);

-- Set a schedule for a specific spider
UPDATE spiders SET schedule_interval = '0 0 * * *' WHERE name = 'climate_news';
-- This means: Run daily at midnight (cron format)
```

**Common schedules:**
- `'0 0 * * *'` - Daily at midnight
- `'0 */6 * * *'` - Every 6 hours
- `'0 0 * * 0'` - Weekly on Sunday
- `'@hourly'` - Every hour
- `'@daily'` - Every day at midnight
- `None` - Manual triggering only (default)

**Option 2: Set in Airflow UI**
1. Go to DAG page
2. Click "Edit" → "Edit DAG"
3. Modify schedule_interval
4. Note: This is temporary and will reset when DAG refreshes

### Monitoring

**View Spider Run:**
1. Click on DAG name
2. See graph view of tasks
3. Click task to see logs
4. Check execution time and status

**View Logs:**
- Each task shows real-time logs
- Logs persist in `airflow/logs/` directory
- Can search and filter logs

**Stats Available:**
- Run duration
- Success/failure rate
- Last run time
- Task dependencies

## Project-Based Access Control (RBAC)

### Creating Project-Specific Roles

**Step 1: Create a Role**
1. Go to Security → List Roles
2. Click "+" to add new role
3. Name: `project_climate_admin`
4. Select permissions:
   - `can_read` on `DAG:climate_*`
   - `can_edit` on `DAG:climate_*`
   - `can_trigger` on `DAG:climate_*`

**Step 2: Create Users**
1. Go to Security → List Users
2. Click "+" to add new user
3. Assign role: `project_climate_admin`

**Step 3: Assign Permissions**
Users will only see and trigger DAGs they have permission for.

### Permission Levels

**Admin:**
- Can see all DAGs
- Can trigger, edit, delete any DAG
- Can manage users and roles

**Project Admin:**
- Can see only project DAGs (filtered by `project:{name}` tag)
- Can trigger and edit project DAGs
- Cannot see other projects

**Project User:**
- Can see project DAGs
- Can trigger project DAGs
- Cannot edit DAG configuration

**Viewer:**
- Can see DAGs
- Cannot trigger or edit

### Example RBAC Setup

```python
# In your DAG generator (airflow/dags/scrapai_spider_dags.py)
# Uncomment the access_control section:

dag = DAG(
    dag_id=dag_id,
    # ... other settings ...
    access_control={
        f'{project}_admin': {'can_read', 'can_edit', 'can_delete'},
        f'{project}_user': {'can_read', 'can_edit'},
    },
)
```

**Then create matching roles in Airflow UI with those exact names.**

## Architecture

```
┌─────────────────────┐
│   Airflow Web UI    │  Port 8080
│   (Browse/Trigger)  │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  Airflow Scheduler  │  Reads DAG files
│  (Manages Schedule) │  every few minutes
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  DAG Generator      │  Queries ScrapAI DB
│  (Python script)    │  Generates DAGs dynamically
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  ScrapAI Database   │  Your spider configs
│  (PostgreSQL)       │
└─────────────────────┘
           │
┌──────────▼──────────┐
│  Bash Operator      │  Executes:
│  (Run Task)         │  ./scrapai crawl {name}
└─────────────────────┘
```

## Troubleshooting

### DAGs not showing up

**Check if DAG file has errors:**
```bash
docker-compose -f docker-compose.airflow.yml exec airflow-webserver \
  python /opt/airflow/dags/scrapai_spider_dags.py
```

**Check scheduler logs:**
```bash
docker-compose -f docker-compose.airflow.yml logs airflow-scheduler
```

**Verify database connection:**
```bash
# Test connection from Airflow container
docker-compose -f docker-compose.airflow.yml exec airflow-webserver \
  python -c "from core.db import get_session; print(get_session())"
```

### Spider crawls failing

**Check task logs in Airflow UI:**
1. Click on failed task (red box)
2. Click "Log" button
3. Look for error messages

**Common issues:**
- Virtual environment not activated → Check bash_command in DAG
- ScrapAI CLI not found → Check SCRAPAI_CLI_PATH environment variable
- Database connection issues → Check DB credentials in .env

**Test spider manually:**
```bash
# SSH into Airflow container
docker-compose -f docker-compose.airflow.yml exec airflow-webserver bash

# Try running spider manually
cd /opt/scrapai
source .venv/bin/activate
./scrapai crawl {spider_name}
```

### Permission denied errors

**Fix Airflow directory permissions:**
```bash
# On host machine
sudo chown -R $(id -u):$(id -g) airflow/logs airflow/dags airflow/plugins

# Or set AIRFLOW_UID in .env
echo "AIRFLOW_UID=$(id -u)" >> .env

# Restart Airflow
docker-compose -f docker-compose.airflow.yml down
docker-compose -f docker-compose.airflow.yml up -d
```

### Database connection issues

**If DAG generator can't connect to ScrapAI database:**

1. Check network connectivity from container:
```bash
docker-compose -f docker-compose.airflow.yml exec airflow-webserver \
  ping -c 3 host.docker.internal
```

2. Use `host.docker.internal` instead of `localhost` in DB_HOST:
```bash
# In .env
DB_HOST=host.docker.internal
```

3. Restart Airflow services:
```bash
docker-compose -f docker-compose.airflow.yml restart
```

## Management Commands

```bash
# Start Airflow
docker-compose -f docker-compose.airflow.yml up -d

# Stop Airflow
docker-compose -f docker-compose.airflow.yml down

# View logs
docker-compose -f docker-compose.airflow.yml logs -f

# Restart specific service
docker-compose -f docker-compose.airflow.yml restart airflow-scheduler

# Reset everything (WARNING: deletes all Airflow data)
docker-compose -f docker-compose.airflow.yml down -v
docker-compose -f docker-compose.airflow.yml up -d

# Access Airflow CLI
docker-compose -f docker-compose.airflow.yml exec airflow-webserver airflow --help

# List all DAGs
docker-compose -f docker-compose.airflow.yml exec airflow-webserver airflow dags list

# Pause/unpause DAG
docker-compose -f docker-compose.airflow.yml exec airflow-webserver \
  airflow dags pause {dag_id}
docker-compose -f docker-compose.airflow.yml exec airflow-webserver \
  airflow dags unpause {dag_id}
```

## Adding Custom Features

### Custom Task After Crawl

Edit `airflow/dags/scrapai_spider_dags.py`:

```python
with dag:
    crawl_task = BashOperator(...)
    verify_task = BashOperator(...)

    # Add your custom task
    notify_task = BashOperator(
        task_id='send_notification',
        bash_command=f'echo "Crawl completed for {spider.name}" | mail -s "Spider Alert" you@example.com',
    )

    # Update dependencies
    crawl_task >> verify_task >> notify_task
```

### Alerting on Failure

Edit DAG default_args:

```python
DEFAULT_DAG_ARGS = {
    # ... existing args ...
    'email': ['your-email@example.com'],
    'email_on_failure': True,
    'email_on_retry': False,
}
```

Configure SMTP in Airflow:
```bash
# Add to docker-compose.airflow.yml environment
AIRFLOW__SMTP__SMTP_HOST: smtp.gmail.com
AIRFLOW__SMTP__SMTP_PORT: 587
AIRFLOW__SMTP__SMTP_USER: your-email@gmail.com
AIRFLOW__SMTP__SMTP_PASSWORD: your-app-password
AIRFLOW__SMTP__SMTP_MAIL_FROM: your-email@gmail.com
```

## Resources

- [Airflow Documentation](https://airflow.apache.org/docs/)
- [DAG Best Practices](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html)
- [Airflow REST API](https://airflow.apache.org/docs/apache-airflow/stable/stable-rest-api-ref.html)
