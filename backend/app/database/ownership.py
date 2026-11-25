"""业务数据所有权检查：沿品牌关联确认当前用户可访问的记录。"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.models import Brand, Job, Observation, Prompt


# 品牌必须属于当前用户；不存在、未归属或属于别人时均返回 404。
async def get_owned_brand(db: AsyncSession, brand_id: int, user_id: int) -> Brand:
    statement = select(Brand).where(Brand.id == brand_id, Brand.user_id == user_id)
    brand = await db.scalar(statement)
    if brand is None:
        raise HTTPException(status_code=404, detail="品牌不存在")
    return brand


# 问题通过所属品牌确定所有者，不暴露其他用户的问题是否存在。
async def get_owned_prompt(db: AsyncSession, prompt_id: int, user_id: int) -> Prompt:
    statement = (
        select(Prompt)
        .join(Brand, Prompt.brand_id == Brand.id)
        .where(Prompt.id == prompt_id, Brand.user_id == user_id)
    )
    prompt = await db.scalar(statement)
    if prompt is None:
        raise HTTPException(status_code=404, detail="问题不存在")
    return prompt


# 回答通过问题和品牌关联确定所有者，不信任前端提交的用户编号。
async def get_owned_observation(
    db: AsyncSession, observation_id: int, user_id: int
) -> Observation:
    statement = (
        select(Observation)
        .join(Prompt, Observation.prompt_id == Prompt.id)
        .join(Brand, Prompt.brand_id == Brand.id)
        .where(Observation.id == observation_id, Brand.user_id == user_id)
    )
    observation = await db.scalar(statement)
    if observation is None:
        raise HTTPException(status_code=404, detail="回答记录不存在")
    return observation


# 任务同样沿问题和品牌检查归属，供详情和取消失败后的状态判断复用。
async def get_owned_job(db: AsyncSession, job_id: int, user_id: int) -> Job:
    statement = (
        select(Job)
        .join(Prompt, Job.prompt_id == Prompt.id)
        .join(Brand, Prompt.brand_id == Brand.id)
        .where(Job.id == job_id, Brand.user_id == user_id)
    )
    job = await db.scalar(statement)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job
