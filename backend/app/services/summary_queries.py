"""品牌回答统计：数据库聚合后只返回一行计数。"""
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.models import Observation, Prompt


# 保留全部样本总数，只有已分析且问题未点名的回答才参与自然提及率。
async def summarize_brand(db: AsyncSession, brand_id: int) -> dict:
    eligible = and_(Observation.mentioned.is_not(None), Observation.prompted.is_(False))
    mentioned = and_(eligible, Observation.mentioned.is_(True))
    statement = (
        select(
            func.count(Observation.id).label("total_samples"),
            func.count(case((eligible, 1))).label("eligible_samples"),
            func.count(case((mentioned, 1))).label("mentioned_samples"),
        )
        .select_from(Observation)
        .join(Prompt, Observation.prompt_id == Prompt.id)
        .where(Prompt.brand_id == brand_id)
    )
    row = (await db.execute(statement)).one()
    return {
        "total_samples": row.total_samples,
        "eligible_samples": row.eligible_samples,
        "mentioned_samples": row.mentioned_samples,
        "mention_rate": row.mentioned_samples / row.eligible_samples if row.eligible_samples else None,
    }
