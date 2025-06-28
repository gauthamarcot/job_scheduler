FROM python:3.10-slim

WORKDIR /tally_job_scheduler

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY . .