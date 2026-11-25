import asyncio
from datetime import timedelta
import logging
from uuid import uuid4

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.session import engine
from backend.app.core.lease_settings import get_lease_settings
from backend.app.database.models import Brand, Job, Observation, Prompt
from backend.app.services.providers import ProviderAnswer, ProviderConfigError, ProviderResponseError, query_deepseek
from backend.app.services.browser_provider import BrowserCollectionError, query_doubao
from backend.app.services.metrics import evaluate
from backend.app.services.redis_cache import delete_key, summary_key
from backend.app.core.timestamps import utc_now
from backend.app.core.observability import log_event, request_context


class JobInputError(ValueError):
    """任务缺少执行所需的输入数据。"""

class LeaseLostError(ValueError):
    """执行权已失效，不能保存迟到结果。"""


# 每次执行的写入必须同时匹配状态、凭证和未到期时间。
def owned_execution(job_id, execution_token, now):
    # SQLite 在 SQL 执行时取 UTC 时间，防止等待写锁期间使用旧时间误判租约有效。
    checked_at = func.strftime("%Y-%m-%d %H:%M:%f", "now") if engine.dialect.name == "sqlite" else now
    return (Job.id == job_id, Job.status == "running",
            Job.execution_token == execution_token, Job.execution_token.is_not(None),
            Job.lease_expires_at > checked_at)


# 原子领取并持久化调用方持有的凭证，提交后才能开始执行。
async def claim_next_job(*, execution_token: str) -> int | None:
    if not execution_token:
        raise ValueError("执行凭证不能为空")
    now = utc_now()
    async with AsyncSession(engine, expire_on_commit=False) as db:
        next_job_id = (select(Job.id).where(Job.status == "queued")
                       .order_by(Job.id).limit(1).scalar_subquery())
        result = await db.execute(update(Job)
            .where(Job.id == next_job_id, Job.status == "queued")
            .values(status="running", error=None, started_at=now, finished_at=None,
                    execution_token=execution_token, heartbeat_at=now,
                    lease_expires_at=now + timedelta(seconds=get_lease_settings().seconds))
            .returning(Job.id))
        job_id = result.scalar_one_or_none()
        await db.commit()
        return job_id


# 未到期且凭证匹配才可续期，已经失去执行权时不能自行复活。
async def renew_job_lease(job_id, execution_token) -> bool:
    now = utc_now()
    async with AsyncSession(engine) as db:
        result = await db.execute(update(Job).where(*owned_execution(job_id, execution_token, now))
            .values(heartbeat_at=now, lease_expires_at=now + timedelta(seconds=get_lease_settings().seconds))
            .returning(Job.id))
        renewed = result.scalar_one_or_none() is not None
        await db.commit()
        return renewed


# 等待模型期间定期用短事务续期，每次完成后归还连接。
async def heartbeat_loop(job_id, execution_token, finished):
    while not finished.is_set():
        try:
            await asyncio.wait_for(finished.wait(), timeout=get_lease_settings().heartbeat_seconds)
            return
        except TimeoutError:
            pass
        if not await renew_job_lease(job_id, execution_token) and not finished.is_set():
            raise LeaseLostError("任务执行权已到期或被撤销")


# 先原子确认执行权，再在同一个事务里保存回答和成功状态。
async def save_job_result(job_id: int, answer: ProviderAnswer, analysis: dict, *, execution_token: str) -> int:
    now = utc_now()
    async with AsyncSession(engine, expire_on_commit=False) as db:
        result = await db.execute(update(Job).where(*owned_execution(job_id, execution_token, now))
            .values(status="succeeded", error=None, finished_at=now, lease_expires_at=None)
            .returning(Job.prompt_id, Job.question_snapshot, Job.request_id))
        inputs = result.first()
        if inputs is None:
            job = await db.get(Job, job_id)
            if job is None:
                raise ValueError("任务不存在")
            if job.question_snapshot is None:
                raise ValueError("任务缺少问题快照")
            if job.status != "running":
                raise LeaseLostError("任务不处于执行中状态")
            raise LeaseLostError("任务执行权已到期或凭证不匹配")
        if inputs.question_snapshot is None:
            raise JobInputError("任务缺少问题快照")
        brand_id = await db.scalar(select(Prompt.brand_id).where(Prompt.id == inputs.prompt_id))
        observation = Observation(prompt_id=inputs.prompt_id, question=inputs.question_snapshot,
            answer=answer.answer, provider=answer.provider, model=answer.model,
            mentioned=analysis["mentioned"], prompted=analysis["prompted"])
        db.add(observation)
        await db.flush()
        await db.execute(update(Job).where(Job.id == job_id).values(observation_id=observation.id, finished_at=utc_now()))
        await db.commit()
        with request_context(inputs.request_id):
            log_event("job.succeeded", job_id=job_id, observation_id=observation.id, status="succeeded")
        if brand_id is not None:
            await delete_key(summary_key(brand_id))
        return observation.id


# 失败与中断也要检查执行权，不能覆盖其他执行或已结束任务。
async def finish_job(job_id, status, error_message, execution_token):
    now = utc_now()
    async with AsyncSession(engine) as db:
        result = await db.execute(update(Job).where(*owned_execution(job_id, execution_token, now))
            .values(status=status, error=error_message, finished_at=now, lease_expires_at=None)
            .returning(Job.request_id))
        row = result.first()
        await db.commit()
        if row is not None:
            with request_context(row.request_id):
                log_event("job." + status, job_id=job_id, status=status)


# 保存已知错误；执行权失效时不再修改，留给到期扫描处理。
async def mark_job_failed(job_id, error_message, *, execution_token: str):
    await finish_job(job_id, "failed", error_message, execution_token)


# 优雅退出只中断自己的有效执行，不重新排队。
async def mark_job_interrupted(job_id, error_message, *, execution_token: str):
    await finish_job(job_id, "interrupted", error_message, execution_token)


# 条件更新过期任务，每批最多一百条；不改旧无凭证任务或活跃任务。
async def recover_expired_jobs(database_engine=None) -> int:
    now = utc_now()
    database_engine = database_engine if database_engine is not None else engine
    checked_at = func.strftime("%Y-%m-%d %H:%M:%f", "now") if database_engine.dialect.name == "sqlite" else now
    expired = (Job.status == "running", Job.execution_token.is_not(None), Job.lease_expires_at <= checked_at)
    async with AsyncSession(database_engine) as db:
        ids = select(Job.id).where(*expired).order_by(Job.id).limit(100).scalar_subquery()
        result = await db.execute(update(Job).where(*expired, Job.id.in_(ids))
            .values(status="interrupted", finished_at=now, lease_expires_at=None,
                    error="执行者未及时续期，任务已中断；上游处理结果未知，未自动重试")
            .returning(Job.id, Job.request_id))
        rows = result.all()
        await db.commit()
    for row in rows:
        with request_context(row.request_id):
            log_event("job.lease_expired", job_id=row.id, status="interrupted")
    return len(rows)


# 服务运行期间扫描到期任务，不以进程重启为理由批量重置 running。
async def recovery_loop(stop_event, database_engine):
    while not stop_event.is_set():
        await recover_expired_jobs(database_engine)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=get_lease_settings().recovery_seconds)
        except TimeoutError:
            pass


# 使用任务快照采集回答、分析提及情况，并保存成功结果。
async def collect_job(
    job_id: int,
    client: httpx.AsyncClient,
    execution_token: str,
    finished: asyncio.Event,
) -> int | None:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        job = await db.get(Job, job_id)
        if job is None:
            raise ValueError("任务不存在")
        if job.status != "running":
            raise LeaseLostError("任务不处于执行中状态")
        if job.execution_token != execution_token or job.lease_expires_at is None or job.lease_expires_at <= utc_now():
            raise LeaseLostError("任务执行权已到期或凭证不匹配")

        if (
            job.question_snapshot is None
            or job.brand_name_snapshot is None
            or job.brand_aliases_snapshot is None
        ):
            raise JobInputError("任务缺少输入快照")

        question = job.question_snapshot
        brand_name = job.brand_name_snapshot
        aliases = list(job.brand_aliases_snapshot)
        request_id = job.request_id
        method = job.collection_method
        owner_id = None
        if method == "browser_doubao":
            owner_id = await db.scalar(select(Brand.user_id).join(Prompt, Prompt.brand_id == Brand.id)
                                       .where(Prompt.id == job.prompt_id))
            if owner_id is None:
                raise JobInputError("浏览器采集任务缺少品牌所有者")

    with request_context(request_id):
        log_event("job.started", job_id=job_id, status="running")
        try:
            if method == "browser_doubao":
                answer = await query_doubao(question, owner_id)
            elif method == "api":
                answer = await query_deepseek(question, client)
            else:
                raise JobInputError("任务采集方式不受支持")
        except (BrowserCollectionError, ProviderConfigError) as error:
            await mark_job_failed(job_id, str(error), execution_token=execution_token)
            return None
        except asyncio.CancelledError:
            await mark_job_interrupted(
                job_id,
                "等待模型时采集被中断，上游处理结果未知，未自动重试",
                execution_token=execution_token,
            )
            raise
        except httpx.TimeoutException:
            await mark_job_failed(
                job_id,
                "等待模型响应超时，上游是否已完成处理未知，请勿盲目重复提交",
                execution_token=execution_token,
            )
            return None
        except httpx.HTTPError:
            await mark_job_failed(
                job_id,
                "模型服务请求失败，请检查网络或服务配置",
                execution_token=execution_token,
            )
            return None
        except ProviderResponseError:
            await mark_job_failed(
                job_id,
                "模型服务返回了无法解析的响应",
                execution_token=execution_token,
            )
            return None
        finally:
            finished.set()
        analysis = evaluate(
            answer=answer.answer,
            question=question,
            brand_name=brand_name,
            aliases=aliases
        )
        observation_id = await save_job_result(job_id, answer, analysis, execution_token=execution_token)
        return observation_id

# 并行等待采集与心跳，失去执行权后取消本地等待，最后等待清理完成。
async def execute_job(job_id: int, client: httpx.AsyncClient, *, execution_token: str) -> int | None:
    finished = asyncio.Event()
    work = asyncio.create_task(collect_job(job_id, client, execution_token, finished), name=f"geo-collect-{job_id}")
    heartbeat = asyncio.create_task(heartbeat_loop(job_id, execution_token, finished), name=f"geo-heartbeat-{job_id}")
    try:
        done, _ = await asyncio.wait([work, heartbeat], return_when=asyncio.FIRST_COMPLETED)
        if work in done:
            return await work
        if heartbeat in done:
            await heartbeat
        return await work
    except LeaseLostError:
        log_event("job.lease_lost", job_id=job_id)
        return None
    finally:
        finished.set()
        for task in (work, heartbeat):
            if not task.done():
                task.cancel()
        await asyncio.gather(work, heartbeat, return_exceptions=True)


# 每次领取生成新凭证，明确传给后续执行和结果写入。
async def worker_loop(client: httpx.AsyncClient, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        execution_token = uuid4().hex
        job_id = await claim_next_job(execution_token=execution_token)
        if job_id is None:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1)
            except TimeoutError:
                pass
            continue
        try:
            await execute_job(job_id, client, execution_token=execution_token)
        except JobInputError as error:
            await mark_job_failed(job_id, str(error), execution_token=execution_token)
        except Exception as error:
            log_event("worker.failed", level=logging.ERROR, job_id=job_id, error_type=type(error).__name__)
            raise
