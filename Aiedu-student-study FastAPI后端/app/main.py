from __future__ import annotations

import uuid
import logging
import json
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.api import (admin, agents, ai, assignments, auth, conversations, course_maps, courses,
                     files, learning, messaging, notifications, prompts, resources)
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import decode_token
from app.db import SessionLocal
from app.integrations.session_store import session_store
from app.models import AIJob, CommunicationMember, CommunicationMessage, User


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Keep deadline notifications working in local development without a separate scheduler."""
    settings = get_settings()
    task = None
    if settings.env == "development":
        async def maintain_teaching_deadlines() -> None:
            from app.worker import deliver_scheduled_notifications, maintain_deadlines
            while True:
                try:
                    await asyncio.to_thread(maintain_deadlines)
                    await asyncio.to_thread(deliver_scheduled_notifications)
                except Exception:
                    logging.getLogger("aiedu.scheduler").exception(
                        "Deadline maintenance iteration failed"
                    )
                await asyncio.sleep(30)

        task = asyncio.create_task(maintain_teaching_deadlines())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="1.0.0", docs_url="/docs",
                  lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "msg": exc.message, "data": None,
                     "request_id": getattr(request.state, "request_id", None)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder({"code": 0, "msg": "字段校验失败", "data": {"errors": exc.errors()},
                     "request_id": getattr(request.state, "request_id", None)},
            ),
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(request: Request, _exc: SQLAlchemyError):
        return JSONResponse(
            status_code=503,
            content={"code": 0, "msg": "数据库暂不可用", "data": None,
                     "request_id": getattr(request.state, "request_id", None)},
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        logging.getLogger("aiedu").exception("Unhandled request error", extra={
            "request_id": getattr(request.state, "request_id", None)
        })
        return JSONResponse(status_code=500, content={"code": 0, "msg": "服务内部错误",
            "data": None, "request_id": getattr(request.state, "request_id", None)})

    for router in (auth.router, admin.router, courses.router, assignments.router,
                   prompts.router, notifications.router, files.router, ai.router,
                   conversations.router, learning.router, resources.router,
                   agents.router, course_maps.router, messaging.router):
        app.include_router(router, prefix=settings.api_prefix)

    @app.get("/health/live", tags=["健康检查"])
    def live():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["健康检查"])
    def ready():
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}

    @app.websocket(f"{settings.api_prefix}/ws/jobs/{{job_id}}")
    async def job_progress(websocket: WebSocket, job_id: int, token: str):
        try:
            payload = decode_token(token)
            if session_store.is_revoked(payload["jti"]):
                raise ValueError("revoked")
            with SessionLocal() as db:
                user = db.get(User, int(payload["sub"]))
                job = db.scalar(select(AIJob).where(AIJob.id == job_id, AIJob.owner_id == int(payload["sub"])))
                if user is None or not user.is_active or job is None:
                    raise ValueError("forbidden")
            await websocket.accept()
            last = None
            while True:
                with SessionLocal() as db:
                    job = db.get(AIJob, job_id)
                    snapshot = {"id": job.id, "status": job.status.value, "progress": job.progress,
                                "result": job.result_data, "error": job.error_message}
                if snapshot != last:
                    await websocket.send_json(snapshot)
                    last = snapshot
                if snapshot["status"] in {"succeeded", "failed", "cancelled"}:
                    await websocket.close()
                    break
                import asyncio
                await asyncio.sleep(1)
        except (KeyError, ValueError):
            await websocket.close(code=4403)
        except WebSocketDisconnect:
            return

    @app.websocket(f"{settings.api_prefix}/ws/messages")
    async def message_stream(websocket: WebSocket, token: str):
        pubsub = None
        redis_client = None
        try:
            payload = decode_token(token)
            if session_store.is_revoked(payload["jti"]):
                raise ValueError("revoked")
            user_id = int(payload["sub"])
            with SessionLocal() as db:
                user = db.get(User, user_id)
                if user is None or not user.is_active:
                    raise ValueError("forbidden")
                last_id = db.scalar(
                    select(func.max(CommunicationMessage.id))
                    .join(CommunicationMember,
                          CommunicationMember.thread_id == CommunicationMessage.thread_id)
                    .where(CommunicationMember.user_id == user_id)
                ) or 0
            await websocket.accept()
            try:
                import redis.asyncio as async_redis
                redis_client = async_redis.from_url(settings.redis_url, decode_responses=True,
                                                    socket_connect_timeout=0.5)
                pubsub = redis_client.pubsub()
                await pubsub.subscribe(f"realtime:messages:{user_id}")
            except Exception:
                pubsub = None
            while True:
                if pubsub is not None:
                    try:
                        event = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
                        if event:
                            value = json.loads(event["data"])
                            await websocket.send_json(value)
                            if value.get("id") is not None:
                                last_id = max(last_id, int(value["id"]))
                    except Exception:
                        pubsub = None
                with SessionLocal() as db:
                    rows = db.scalars(
                        select(CommunicationMessage)
                        .join(CommunicationMember,
                              CommunicationMember.thread_id == CommunicationMessage.thread_id)
                        .where(CommunicationMember.user_id == user_id,
                               CommunicationMessage.id > last_id,
                               CommunicationMessage.sender_id != user_id)
                        .order_by(CommunicationMessage.id).limit(100)
                    ).all()
                    for row in rows:
                        await websocket.send_json({"id": row.id, "thread_id": row.thread_id,
                                                   "sender_id": row.sender_id, "body": row.body,
                                                   "message_type": row.message_type,
                                                   "created_at": row.created_at.isoformat()})
                        last_id = max(last_id, row.id)
                import asyncio
                await asyncio.sleep(1)
        except (KeyError, ValueError):
            await websocket.close(code=4403)
        except WebSocketDisconnect:
            return
        finally:
            if pubsub is not None:
                await pubsub.aclose()
            if redis_client is not None:
                await redis_client.aclose()

    return app


app = create_app()


def run() -> None:
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=9091, reload=False)
