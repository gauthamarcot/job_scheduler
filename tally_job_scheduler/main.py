from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from .routes import jobs_routes
from .services.ws_services import ConnectionManager
from .utils import get_session

app = FastAPI(swagger_ui_parameters={"syntaxHighlight": {"theme": "obsidian"}})
manager = ConnectionManager()

app.include_router(jobs_routes.router)


@app.get("/health")
async def health(session: Session = Depends(get_session)):
    try:
        session.exec(select(1)).one()
        return {"api_status": "ok",
                "db_status": "ok"}
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "api_status": "ok",
                "db_status": "error",
                "error_message": "Could not connect to the database.",
                "details": str(e)
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "api_status": "error",
                "db_status": "unknown",
                "error_message": "An unexpected error occurred.",
                "details": str(e)
            }
        )


@app.websocket("/jobs/ws/stream")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    print(f"Total clients: {len(manager.active_connections)}")
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print(f"Client disconnected {len(manager.active_connections)}")