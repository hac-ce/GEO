from backend.app.core.timestamps import timestamp_to_string


# 将品牌 ORM 对象转换成接口返回的字典。
def brand_to_dict(brand):
    return {
        "id" : brand.id,
        "name" : brand.name,
        "aliases" : brand.aliases,
        "domain" : brand.domain
    }

def question_to_dict(Prompt):
    return {
        "id": Prompt.id,
        "brand_id" : Prompt.brand_id,
        "question" : Prompt.question
    }

# 将回答记录转换成接口返回的字典。
def observation_to_dict(observation):
    return {
        "id": observation.id,
        "prompt_id": observation.prompt_id,
        "question": observation.question,
        "answer": observation.answer,
        "mentioned": observation.mentioned,
        "prompted": observation.prompted,
        "created_at": timestamp_to_string(observation.created_at),
        "provider": observation.provider,
        "model": observation.model,
    }

# 将采集任务转换成接口返回的字典。
def job_to_dict(job):
    return {
        "id": job.id,
        "prompt_id": job.prompt_id,
        "status": job.status,
        "error": job.error,
        "observation_id": job.observation_id,
        "created_at": timestamp_to_string(job.created_at),
        "started_at": timestamp_to_string(job.started_at),
        "finished_at": timestamp_to_string(job.finished_at),
        "request_id": job.request_id,
        "collection_method": job.collection_method,
    }
