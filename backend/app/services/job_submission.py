"""以持久化唯一记录保护任务创建，不用缓存决定是否再次调用模型。"""
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import select

from backend.app.database.models import JobSubmission
from backend.app.database.ownership import get_owned_job


# 编号只保存摘要；相同用户重用编号时必须仍指向同一个问题。
def submission_digest(key: str | None) -> str | None:
    return sha256(key.encode("ascii")).hexdigest() if key is not None else None


# 权限检查在 API 层先执行；重放时再次按归属读取最新任务状态。
async def find_submission(db, user_id: int, digest: str | None, prompt_id: int, collection_method: str = "api"):
    if digest is None:
        return None
    record = await db.scalar(select(JobSubmission).where(
        JobSubmission.user_id == user_id, JobSubmission.key_hash == digest,
    ))
    if record is None:
        return None
    job = await get_owned_job(db, record.job_id, user_id)
    if job.prompt_id != prompt_id or job.collection_method != collection_method:
        raise HTTPException(409, "这个提交编号已经用于其他问题或采集方式，请为新操作生成新编号")
    return job
