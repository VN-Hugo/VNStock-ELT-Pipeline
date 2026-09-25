FROM apache/airflow:2.10.5-python3.12

# Pipeline libraries + dbt live in their own virtualenv so their pins never fight Airflow's constraints.
# The DAG calls /opt/pipeline-venv/bin/python and /opt/pipeline-venv/bin/dbt.
USER root
RUN python -m venv /opt/pipeline-venv && chown -R airflow: /opt/pipeline-venv
USER airflow
COPY requirements.txt /tmp/requirements.txt
RUN /opt/pipeline-venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt
