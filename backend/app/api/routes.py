from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.database.session import get_db
from backend.app.core.auth import current_active_user
from backend.app.database.models import Brand, Prompt, Observation, Job, User, JobSubmission
from sqlalchemy.exc import IntegrityError
from backend.app.database.ownership import (
    get_owned_brand,
    get_owned_prompt,
    get_owned_observation,
    get_owned_job,
)
from backend.app.services.serializers import (
    brand_to_dict,
    question_to_dict,
    observation_to_dict,
    job_to_dict
)
from backend.app.services.metrics import evaluate
from backend.app.services.summary_queries import summarize_brand
from backend.app.services.providers import ProviderConfigError, ProviderResponseError, query_deepseek
from backend.app.services.browser_provider import settings as browser_settings
import httpx
from typing import Literal
from fastapi import Query
from backend.app.services.redis_cache import delete_key, get_json, set_json, summary_key
from backend.app.core.timestamps import utc_now
from backend.app.core.observability import current_request_id, log_event
from backend.app.api.health import router as health_router
from backend.app.services.job_submission import find_submission, submission_digest
from backend.app.core.rate_limits import limit_collection

router = APIRouter(prefix="/api")
router.include_router(health_router)

# 校验创建或修改品牌时提交的数据。
class BrandInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    aliases: list[str] = Field()
    domain: str

# 校验提交的监测问题。
class PromptInput(BaseModel):
    question: str = Field(min_length=1, max_length=500)

# 校验提交的回答内容。
class AnswerInput(BaseModel):
    answer: str = Field(min_length=1, max_length=30000)

# 只查询当前登录用户拥有的品牌。
@router.get("/brands")
async def list_brands(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str = Query(default="", max_length=80),
):
    statement = select(Brand.id, Brand.name, Brand.aliases, Brand.domain).where(Brand.user_id == user.id)
    keyword = q.strip()
    if keyword:
        statement = statement.where(or_(
            Brand.name.icontains(keyword, autoescape=True),
            Brand.domain.icontains(keyword, autoescape=True),
        ))
    statement = statement.order_by(Brand.id).offset(offset).limit(limit)
    query_result = await db.execute(statement)
    return [dict(row) for row in query_result.mappings()]

# 根据编号查询品牌，不存在时返回 404。
@router.get("/brands/{brand_id}")
async def get_brand(
    brand_id: int,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    brand = await get_owned_brand(db, brand_id, user.id)
    return brand_to_dict(brand)

# 汇总指定品牌的回答，计算自然提及率。
@router.get("/brands/{brand_id}/summary")
async def brand_summary(
    brand_id: int,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # 缓存命中也不能绕过权限检查，必须先确认品牌归属。
    await get_owned_brand(db, brand_id, user.id)
    cached = await get_json(summary_key(brand_id))
    if cached is not None:
        return cached
    result = await summarize_brand(db, brand_id)
    await set_json(summary_key(brand_id), result)
    return result


# 按编号升序分页查询品牌问题。
@router.get("/brands/{brand_id}/prompts")
async def list_prompts(
    brand_id: int,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str = Query(default="", max_length=500),
):
    await get_owned_brand(db, brand_id, user.id)
    statement = select(Prompt).where(Prompt.brand_id == brand_id)
    if q.strip():
        statement = statement.where(Prompt.question.icontains(q.strip(), autoescape=True))
    statement = statement.order_by(Prompt.id).offset(offset).limit(limit)
    query_result = await db.scalars(statement)
    rows = query_result.all()
    result = []
    for row in rows:
        prompt_dict = question_to_dict(row)
        result.append(prompt_dict)
    return result

# 查询指定问题的历史回答。
@router.get("/prompts/{prompt_id}/observations")
async def list_observations(
    prompt_id: int,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    await get_owned_prompt(db, prompt_id, user.id)
    statement = (select(Observation).where(Observation.prompt_id == prompt_id)
                 .order_by(Observation.id.desc()).offset(offset).limit(limit))
    query_result = await db.scalars(statement)
    rows = query_result.all()
    result = []
    for row in rows:
        observation_dict = observation_to_dict(row)
        result.append(observation_dict)
    return result

# 品牌回答直接分页查询，不由前端逐个问题拉取并合并。
@router.get("/brands/{brand_id}/observations")
async def list_brand_observations(
    brand_id: int,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    await get_owned_brand(db, brand_id, user.id)
    statement = (select(Observation).join(Prompt, Observation.prompt_id == Prompt.id)
                 .where(Prompt.brand_id == brand_id).order_by(Observation.id.desc())
                 .offset(offset).limit(limit))
    rows = (await db.scalars(statement)).all()
    return [observation_to_dict(row) for row in rows]

# 按状态查询采集任务，按编号倒序分页返回。
@router.get("/jobs")
async def list_jobs(
    status: Literal[
        "queued", "running", "succeeded", "failed", "interrupted", "cancelled"
    ] | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db)
):
    statement = (
        select(Job)
        .join(Prompt, Job.prompt_id == Prompt.id)
        .join(Brand, Prompt.brand_id == Brand.id)
        .where(Brand.user_id == user.id)
    )
    if status is not None:
        statement = statement.where(Job.status == status)
    statement = (
    statement
    .order_by(Job.id.desc())
    .offset(offset)
    .limit(limit)
    )
    query_result = await db.scalars(statement)
    rows = query_result.all()
    result = []
    for row in rows:
        result.append(job_to_dict(row))
    return result

@router.get("/observations/{observation_id}")
async def get_observation(
    observation_id : int,
    user: User = Depends(current_active_user),
    db : AsyncSession = Depends(get_db)
):
    observation = await get_owned_observation(db, observation_id, user.id)
    return observation_to_dict(observation)

# 原子取消仍在排队的任务，已经领取或结束时返回冲突。
@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: int,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # rollback 会使 ORM 属性过期，提前复制用户编号供失败分支使用。
    user_id = user.id
    owned_prompt_ids = (
        select(Prompt.id)
        .join(Brand, Prompt.brand_id == Brand.id)
        .where(Brand.user_id == user_id)
    )
    statement = (
        update(Job)
        .where(
            Job.id == job_id,
            Job.status == "queued",
            Job.prompt_id.in_(owned_prompt_ids),
        )
        .values(status="cancelled", error="用户取消任务", finished_at=utc_now())
        .returning(Job)
    )
    result = await db.execute(statement)
    job = result.scalar_one_or_none()
    if job is None:
        await db.rollback()
        await get_owned_job(db, job_id, user_id)
        raise HTTPException(status_code=409, detail="只有排队中的任务可以取消")

    await db.commit()
    log_event("job.cancelled", user_id=user_id, job_id=job.id, status=job.status)
    return job_to_dict(job)

# 根据编号查询采集任务，不存在时返回 404。
@router.get("/jobs/{job_id}")
async def get_job(
    job_id: int,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db)
):
    job = await get_owned_job(db, job_id, user.id)
    return job_to_dict(job)

# 修改品牌信息
@router.put("/brands/{brand_id}")
async def update_brand(
    brand_id: int,
    data: BrandInput,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    brand = await get_owned_brand(db, brand_id, user.id)
    brand.name = data.name
    brand.aliases = data.aliases
    brand.domain = data.domain
    await db.commit()
    log_event("brand.updated", user_id=user.id, brand_id=brand.id)
    return brand_to_dict(brand)

# 根据问题编号修改监测问题
@router.put("/prompts/{prompt_id}")
async def update_prompt(
    prompt_id: int,
    data: PromptInput,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db)
):
    prompt = await get_owned_prompt(db, prompt_id, user.id)
    prompt.question = data.question
    await db.commit()
    log_event("prompt.updated", user_id=user.id, prompt_id=prompt.id)
    return question_to_dict(prompt)

# 创建属于当前登录用户的品牌并提交到数据库。
@router.post("/brands", status_code=201)
async def create_brand(
    data: BrandInput,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    brand = Brand(**data.model_dump(), user_id=user.id)
    db.add(brand)
    await db.commit()
    log_event("brand.created", user_id=user.id, brand_id=brand.id)
    return brand_to_dict(brand)

# 创建品牌监测问题接口
@router.post("/brands/{brand_id}/prompts", status_code=201)
async def create_prompt(
    brand_id: int,
    data: PromptInput,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db)
):
    await get_owned_brand(db, brand_id, user.id)
    prompt = Prompt(
        brand_id = brand_id,
        question = data.question
    )
    db.add(prompt)
    await db.commit()
    log_event("prompt.created", user_id=user.id, brand_id=brand_id, prompt_id=prompt.id)
    return question_to_dict(prompt)

# 为指定问题创建一条待执行的采集任务。
@router.post("/prompts/{prompt_id}/jobs", status_code=202)
async def create_job(
    prompt_id: int,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
    collection_method: Literal["api", "browser_doubao"] = Query(default="api"),
):
    # 先确认问题及其所属品牌都对当前用户可见，再保存提交时快照。
    prompt = await get_owned_prompt(db, prompt_id, user.id)
    brand = await get_owned_brand(db, prompt.brand_id, user.id)
    user_id = user.id
    digest = submission_digest(idempotency_key)
    existing = await find_submission(db, user_id, digest, prompt_id, collection_method)
    if existing is not None:
        response.status_code = 200
        response.headers["Idempotency-Replayed"] = "true"
        log_event("job.replayed", user_id=user_id, job_id=existing.id)
        return job_to_dict(existing)
    inputs = dict(question_snapshot=prompt.question, brand_name_snapshot=brand.name,
                  brand_aliases_snapshot=list(brand.aliases))
    if collection_method == "browser_doubao":
        if getattr(request.app.state, "runtime_mode", "live") == "demo":
            raise HTTPException(409, "演示模式不访问真实豆包，请在本机正式后端使用浏览器渠道")
        if not browser_settings().enabled:
            raise HTTPException(409, "浏览器采集未启用，请在后端配置并重启")
    await db.rollback()
    await limit_collection(request, user_id)
    job = Job(
        prompt_id=prompt_id,
        status="queued",
        request_id=current_request_id(),
        collection_method=collection_method,
        **inputs,
    )
    try:
        db.add(job)
        await db.flush()
        if digest is not None:
            db.add(JobSubmission(user_id=user_id, key_hash=digest, job_id=job.id))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await find_submission(db, user_id, digest, prompt_id, collection_method)
        if existing is None:
            raise
        response.status_code = 200
        response.headers["Idempotency-Replayed"] = "true"
        log_event("job.replayed", user_id=user_id, job_id=existing.id)
        return job_to_dict(existing)
    log_event("job.queued", user_id=user_id, job_id=job.id, prompt_id=prompt_id, status=job.status)
    return job_to_dict(job)

# 调用 DeepSeek 保存回答，并返回本次品牌提及分析。
@router.post("/prompts/{prompt_id}/observations", status_code=201)
async def create_observation(
    prompt_id: int,
    request: Request,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db)
):
    prompt = await get_owned_prompt(db, prompt_id, user.id)
    brand = await get_owned_brand(db, prompt.brand_id, user.id)
    brand_id = brand.id
    user_id = user.id
    question = prompt.question
    brand_name = brand.name
    aliases = list(brand.aliases)
    # 已复制本次采集所需数据，结束读取事务后再等待模型。
    await db.rollback()
    await limit_collection(request, user_id)
    client = request.app.state.http_client

    try:
        response = await query_deepseek(question, client)
    except ProviderConfigError as error:
        raise HTTPException(503, str(error)) from None
    except httpx.TimeoutException as error:
        log_event("collection.failed", user_id=user_id, prompt_id=prompt_id, error_type=type(error).__name__)
        raise HTTPException(
            status_code=504,
            detail="等待模型响应超时，请稍后查看情况再决定是否重试"
        )
    except httpx.HTTPError as error:
        log_event("collection.failed", user_id=user_id, prompt_id=prompt_id, error_type=type(error).__name__)
        raise HTTPException(
            status_code=502,
            detail="模型服务请求失败，请检查服务配置或网络"
        )
    except ProviderResponseError as error:
        log_event("collection.failed", user_id=user_id, prompt_id=prompt_id, error_type=type(error).__name__)
        raise HTTPException(
            status_code=502,
            detail="模型服务返回了无法解析的响应"
        )
    analysis = evaluate(
        answer=response.answer,
        question=question,
        brand_name=brand_name,
        aliases=aliases
    )
    observation = Observation(
        prompt_id = prompt_id,
        question = question,
        answer = response.answer,
        provider=response.provider,
        model=response.model,
        mentioned=analysis["mentioned"],
        prompted=analysis["prompted"]
    )
    db.add(observation)
    await db.commit()
    log_event("observation.created", user_id=user_id, prompt_id=prompt_id, observation_id=observation.id)
    await delete_key(summary_key(brand_id))
    result = observation_to_dict(observation)
    return result
