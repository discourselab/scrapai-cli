#!/usr/bin/env python3
"""
Airflow API Utility for ScrapAI

Usage:
    python airflow_api.py list                      # List all DAGs
    python airflow_api.py list --project brown      # List brown project DAGs
    python airflow_api.py unpause <dag_id>          # Unpause a DAG
    python airflow_api.py unpause --all             # Unpause all DAGs
    python airflow_api.py trigger <dag_id>          # Trigger a DAG
    python airflow_api.py trigger --all             # Trigger all DAGs
    python airflow_api.py trigger --all --limit 10  # Trigger first 10 DAGs
    python airflow_api.py status <dag_id>           # Check DAG run status
    python airflow_api.py status --running          # Show all running DAGs
"""

import argparse
import requests
import json
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Configuration
AIRFLOW_URL = os.getenv('AIRFLOW_URL', 'http://localhost:8080')
AIRFLOW_USER = os.getenv('AIRFLOW_USER', 'admin')
AIRFLOW_PASSWORD = os.getenv('_AIRFLOW_WWW_USER_PASSWORD', 'admin123')

# Default project filter
DEFAULT_PROJECT = 'brown'


def get_auth():
    return (AIRFLOW_USER, AIRFLOW_PASSWORD)


def api_get(endpoint, params=None):
    """GET request to Airflow API"""
    url = f"{AIRFLOW_URL}/api/v1/{endpoint}"
    response = requests.get(url, auth=get_auth(), params=params)
    response.raise_for_status()
    return response.json()


def api_post(endpoint, data=None):
    """POST request to Airflow API"""
    url = f"{AIRFLOW_URL}/api/v1/{endpoint}"
    response = requests.post(url, auth=get_auth(), json=data or {})
    response.raise_for_status()
    return response.json()


def api_patch(endpoint, data):
    """PATCH request to Airflow API"""
    url = f"{AIRFLOW_URL}/api/v1/{endpoint}"
    response = requests.patch(url, auth=get_auth(), json=data)
    response.raise_for_status()
    return response.json()


# ============ LIST ============

def list_dags(project=None, limit=100):
    """List all DAGs, optionally filtered by project tag"""
    params = {'limit': limit}
    if project:
        params['tags'] = f'project:{project}'

    result = api_get('dags', params)
    return result.get('dags', [])


def cmd_list(args):
    """Command: list DAGs"""
    dags = list_dags(project=args.project, limit=args.limit)

    if not dags:
        print(f"No DAGs found" + (f" for project '{args.project}'" if args.project else ""))
        return

    print(f"{'DAG ID':<50} {'Paused':<8} {'Active':<8}")
    print("-" * 70)

    for dag in dags:
        status = "Yes" if dag['is_paused'] else "No"
        active = "Yes" if dag['is_active'] else "No"
        print(f"{dag['dag_id']:<50} {status:<8} {active:<8}")

    print(f"\nTotal: {len(dags)} DAGs")


# ============ UNPAUSE ============

def unpause_dag(dag_id):
    """Unpause a single DAG"""
    result = api_patch(f'dags/{dag_id}', {'is_paused': False})
    return result


def cmd_unpause(args):
    """Command: unpause DAG(s)"""
    if args.all:
        dags = list_dags(project=args.project, limit=args.limit)
        paused_dags = [d for d in dags if d['is_paused']]

        if not paused_dags:
            print("No paused DAGs found")
            return

        print(f"Unpausing {len(paused_dags)} DAGs...")
        for dag in paused_dags:
            try:
                unpause_dag(dag['dag_id'])
                print(f"  ✓ {dag['dag_id']}")
            except Exception as e:
                print(f"  ✗ {dag['dag_id']}: {e}")

        print(f"\nDone. Unpaused {len(paused_dags)} DAGs.")

    elif args.dag_id:
        try:
            unpause_dag(args.dag_id)
            print(f"✓ Unpaused: {args.dag_id}")
        except Exception as e:
            print(f"✗ Error: {e}")

    else:
        print("Specify --all or <dag_id>")


# ============ TRIGGER ============

def trigger_dag(dag_id):
    """Trigger a single DAG"""
    result = api_post(f'dags/{dag_id}/dagRuns')
    return result


def cmd_trigger(args):
    """Command: trigger DAG(s)"""
    if args.all:
        dags = list_dags(project=args.project, limit=args.limit)

        # Filter to only active, unpaused DAGs
        active_dags = [d for d in dags if d['is_active'] and not d['is_paused']]

        if not active_dags:
            print("No active unpaused DAGs found. Run 'unpause --all' first.")
            return

        print(f"Triggering {len(active_dags)} DAGs...")
        triggered = 0
        for dag in active_dags:
            try:
                trigger_dag(dag['dag_id'])
                print(f"  ✓ {dag['dag_id']}")
                triggered += 1
            except Exception as e:
                print(f"  ✗ {dag['dag_id']}: {e}")

        print(f"\nDone. Triggered {triggered} DAGs.")

    elif args.dag_id:
        try:
            result = trigger_dag(args.dag_id)
            print(f"✓ Triggered: {args.dag_id}")
            print(f"  Run ID: {result.get('dag_run_id')}")
            print(f"  State: {result.get('state')}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 409:
                print(f"✗ DAG already running or queued: {args.dag_id}")
            else:
                print(f"✗ Error: {e}")

    else:
        print("Specify --all or <dag_id>")


# ============ STATUS ============

def get_dag_runs(dag_id, limit=5):
    """Get recent DAG runs"""
    result = api_get(f'dags/{dag_id}/dagRuns', {'limit': limit, 'order_by': '-execution_date'})
    return result.get('dag_runs', [])


def get_running_dags(project=None):
    """Get all currently running DAG runs"""
    params = {'state': 'running', 'limit': 100}
    result = api_get('dags/~/dagRuns', params)
    runs = result.get('dag_runs', [])

    if project:
        runs = [r for r in runs if r['dag_id'].startswith(f'{project}_')]

    return runs


def cmd_status(args):
    """Command: check DAG status"""
    if args.running:
        runs = get_running_dags(project=args.project)

        if not runs:
            print("No DAGs currently running")
            return

        print(f"{'DAG ID':<50} {'State':<12} {'Started':<20}")
        print("-" * 85)

        for run in runs:
            started = run.get('start_date', 'N/A')
            if started and started != 'N/A':
                started = started[:19].replace('T', ' ')
            print(f"{run['dag_id']:<50} {run['state']:<12} {started:<20}")

        print(f"\nTotal: {len(runs)} running")

    elif args.dag_id:
        runs = get_dag_runs(args.dag_id, limit=args.limit)

        if not runs:
            print(f"No runs found for {args.dag_id}")
            return

        print(f"Recent runs for {args.dag_id}:\n")
        print(f"{'Run ID':<45} {'State':<12} {'Date':<20}")
        print("-" * 80)

        for run in runs:
            run_id = run['dag_run_id'][:42] + '...' if len(run['dag_run_id']) > 45 else run['dag_run_id']
            date = run.get('execution_date', 'N/A')[:19].replace('T', ' ')
            print(f"{run_id:<45} {run['state']:<12} {date:<20}")

    else:
        print("Specify --running or <dag_id>")


# ============ MAIN ============

def main():
    parser = argparse.ArgumentParser(description='Airflow API Utility for ScrapAI')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # List command
    list_parser = subparsers.add_parser('list', help='List DAGs')
    list_parser.add_argument('--project', default=DEFAULT_PROJECT, help=f'Project filter (default: {DEFAULT_PROJECT})')
    list_parser.add_argument('--limit', type=int, default=200, help='Max DAGs to list')

    # Unpause command
    unpause_parser = subparsers.add_parser('unpause', help='Unpause DAG(s)')
    unpause_parser.add_argument('dag_id', nargs='?', help='DAG ID to unpause')
    unpause_parser.add_argument('--all', action='store_true', help='Unpause all DAGs')
    unpause_parser.add_argument('--project', default=DEFAULT_PROJECT, help=f'Project filter (default: {DEFAULT_PROJECT})')
    unpause_parser.add_argument('--limit', type=int, default=200, help='Max DAGs to unpause')

    # Trigger command
    trigger_parser = subparsers.add_parser('trigger', help='Trigger DAG(s)')
    trigger_parser.add_argument('dag_id', nargs='?', help='DAG ID to trigger')
    trigger_parser.add_argument('--all', action='store_true', help='Trigger all DAGs')
    trigger_parser.add_argument('--project', default=DEFAULT_PROJECT, help=f'Project filter (default: {DEFAULT_PROJECT})')
    trigger_parser.add_argument('--limit', type=int, default=200, help='Max DAGs to trigger')

    # Status command
    status_parser = subparsers.add_parser('status', help='Check DAG status')
    status_parser.add_argument('dag_id', nargs='?', help='DAG ID to check')
    status_parser.add_argument('--running', action='store_true', help='Show all running DAGs')
    status_parser.add_argument('--project', default=DEFAULT_PROJECT, help=f'Project filter (default: {DEFAULT_PROJECT})')
    status_parser.add_argument('--limit', type=int, default=5, help='Max runs to show')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == 'list':
            cmd_list(args)
        elif args.command == 'unpause':
            cmd_unpause(args)
        elif args.command == 'trigger':
            cmd_trigger(args)
        elif args.command == 'status':
            cmd_status(args)
    except requests.exceptions.ConnectionError:
        print(f"✗ Cannot connect to Airflow at {AIRFLOW_URL}")
        print("  Is Airflow running? Try: sudo docker compose -f docker-compose.airflow.yml up -d")
    except requests.exceptions.HTTPError as e:
        print(f"✗ API Error: {e}")


if __name__ == '__main__':
    main()
