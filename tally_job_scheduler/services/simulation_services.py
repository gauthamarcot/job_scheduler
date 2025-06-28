import asyncio
import json
import random
from datetime import datetime

from sqlmodel import select

from tally_job_scheduler.models.jobs import Job, JobLog
from tally_job_scheduler.services.ws_services import ConnectionManager
from tally_job_scheduler.utils import get_session

manager = ConnectionManager()


async def simulate_job_process():
    while True:  #infinate loop to check a new jobs and excuting
        await asyncio.sleep(10)
        with get_session() as session:
            stmt = select(Job).where(Job.status == "pending").order_by(Job.priority)
            job_to_process = session.exec(stmt).first()
            if job_to_process:
                job_to_process.status = "running"
                job_to_process.started_at = datetime.utcnow()
                session.add(job_to_process)
                session.commit()
                session.refresh(job_to_process)

                status_update = {"job_id": str(job_to_process.id), "status": job_to_process.status}
                await manager.broadcast(json.dumps(status_update))
                print(f"Simulating job: {job_to_process.job_id}")

                log_messages = [
                    f"Starting job type '{job_to_process.type}'.",
                    "Fetching resources...",
                    "Processing data chunk 1 of 3.",
                    "Processing data chunk 2 of 3.",
                    "Processing data chunk 3 of 3.",
                    "Finalizing results..."
                ]
                for msg in log_messages:
                    await asyncio.sleep(random.uniform(1, 3))
                    log_entry = JobLog(job_id=job_to_process.job_id, message=msg)
                    session.add(log_entry)
                    session.commit()
                    log_update = {"job_id": str(job_to_process.job_id), "log": msg}
                    await manager.broadcast(json.dumps(log_update))

                final_status = random.choice(["completed", "failed"])
                job_to_process.status = final_status
                job_to_process.completed_at = datetime.utcnow()
                session.add(job_to_process)
                session.commit()

                final_message = "Job finished successfully." if final_status == "completed" else ("Job failed due to a "
                                                                                                  "simulated error.")
                final_log = JobLog(job_id=job_to_process.job_id, message=final_message,
                                   log_level="INFO" if final_status == "completed" else "ERROR")
                session.add(final_log)
                session.commit()

                await manager.broadcast(json.dumps({"job_id": str(job_to_process.job_id), "log": final_message}))
                await manager.broadcast(json.dumps({"job_id": str(job_to_process.job_id), "status": final_status}))
                print(f"Finished simulating job: {job_to_process.job_id} with status {final_status}")
