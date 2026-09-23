"""Daily VNStock ELT: check_day -> ingest_vnstock -> load_bronze -> dbt_silver -> dbt_gold -> notify.

Pipeline tasks run the project CLI (run_pipeline.py) and dbt from a separate virtualenv
(PIPELINE_PYTHON / DBT_BIN) so vnstock and dbt dependencies never clash with Airflow's.
"""
from __future__ import annotations

import os
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.state import TaskInstanceState
from airflow.utils.trigger_rule import TriggerRule

PROJECT_DIR = os.getenv("PROJECT_DIR", "/opt/project")
PIPELINE_PYTHON = os.getenv("PIPELINE_PYTHON", "/opt/pipeline-venv/bin/python")
DBT_BIN = os.getenv("DBT_BIN", "/opt/pipeline-venv/bin/dbt")
STAGING_DIR = "/tmp/vnstock_staging/{{ dag_run.id }}"
VN_TZ = pendulum.timezone("Asia/Ho_Chi_Minh")
DBT = f"{DBT_BIN} build --project-dir dbt --profiles-dir dbt --target-path /tmp/dbt_target --log-path /tmp/dbt_logs"


def _notify(**context) -> None:
    from src.notify import notify

    dag_run = context["dag_run"]
    states = {ti.task_id: ti.state for ti in dag_run.get_task_instances() if ti.task_id != "notify"}
    failed = [task for task, state in states.items() if state in (TaskInstanceState.FAILED, TaskInstanceState.UPSTREAM_FAILED)]
    run = f"{dag_run.dag_id} / {dag_run.run_id}"

    if failed:
        notify(f"❌ VNStock ELT failed: {', '.join(failed)}", f"Run: {run}\nCheck the task logs in Airflow.")
        # notify is the leaf task, so without this the DAG run would be marked success
        raise AirflowFailException(f"Upstream tasks failed: {failed}")
    if states.get("check_day") == TaskInstanceState.SKIPPED:
        notify("⏭️ VNStock ELT skipped", f"Run: {run}\nNot a trading day or market data not published yet.")
    else:
        notify("✅ VNStock ELT succeeded", f"Run: {run}\nBronze loaded, Silver and Gold rebuilt.")


with DAG(
    dag_id="vnstock_elt",
    description="vnstock -> Supabase bronze -> dbt silver -> dbt gold",
    # 15:30 VN time on weekdays, after the ATC session closes at 14:45
    schedule="30 15 * * 1-5",
    start_date=pendulum.datetime(2026, 1, 1, tz=VN_TZ),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    params={"force": False, "full_refresh": False},
    tags=["vnstock", "elt", "dbt"],
) as dag:
    check_day = BashOperator(
        task_id="check_day",
        # Exit code 99 = not a trading day -> task and downstream are skipped (not failed).
        # Trigger manually with {"force": true} to bypass, e.g. for a backfill.
        bash_command=(
            "{% if params.force %}echo 'force=true: skipping trading-day check'"
            "{% else %}" + PIPELINE_PYTHON + " run_pipeline.py check-day"
            " --date {{ data_interval_end.in_timezone('Asia/Ho_Chi_Minh').to_date_string() }}{% endif %}"
        ),
        cwd=PROJECT_DIR,
        retries=0,
    )

    ingest_vnstock = BashOperator(
        task_id="ingest_vnstock",
        bash_command=f"{PIPELINE_PYTHON} run_pipeline.py ingest --staging-dir {STAGING_DIR}"
        "{% if params.full_refresh %} --full-refresh{% endif %}",
        cwd=PROJECT_DIR,
    )

    load_bronze = BashOperator(
        task_id="load_bronze",
        bash_command=f"{PIPELINE_PYTHON} run_pipeline.py load-bronze --staging-dir {STAGING_DIR} --batch-id '{{{{ run_id }}}}'",
        cwd=PROJECT_DIR,
    )

    dbt_silver = BashOperator(
        task_id="dbt_silver",
        # Source tests on bronze, Silver models and their tests
        bash_command=f"{DBT} --select source:bronze path:models/silver",
        cwd=PROJECT_DIR,
    )

    dbt_gold = BashOperator(
        task_id="dbt_gold",
        bash_command=f"{DBT} --select path:models/gold",
        cwd=PROJECT_DIR,
    )

    notify = PythonOperator(
        task_id="notify",
        python_callable=_notify,
        trigger_rule=TriggerRule.ALL_DONE,
        retries=0,
    )

    check_day >> ingest_vnstock >> load_bronze >> dbt_silver >> dbt_gold >> notify
