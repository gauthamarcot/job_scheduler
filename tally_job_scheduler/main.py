from fastapi import FastAPI
from routes import health_routes, jobs_routes

app = FastAPI()


app.include_router(jobs_routes.router)
app.include_router(health_routes.router)

