import os
from dataclasses import dataclass
import httpx
from dotenv import load_dotenv
from backend.app.core.observability import log_event

load_dotenv()
key = os.getenv("DEEPSEEK_API_KEY")

class ProviderResponseError(RuntimeError):
    """模型服务返回的数据结构不符合预期。"""


class ProviderConfigError(RuntimeError):
    """所选模型渠道尚未配置。"""


@dataclass(frozen=True)
class ProviderAnswer:
    """一次模型调用的回答及来源信息，不包含密钥或请求头。"""
    answer: str
    provider: str
    model: str | None


def extract_answer(result: object) -> str:
    """检查模型响应结构，并提取回答文本。"""
    if not isinstance(result, dict):
        raise ProviderResponseError("模型响应不是 JSON 对象")

    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderResponseError("模型响应缺少 choices")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ProviderResponseError("choices[0] 不是对象")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ProviderResponseError("模型响应缺少 message")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ProviderResponseError("模型响应缺少有效回答")

    return content

headers = {
    "Authorization": f"Bearer {key}"
}

# 将问题发送给 DeepSeek，返回回答文本和响应中的模型来源。
async def query_deepseek(
    question: str,
    client: httpx.AsyncClient
) -> ProviderAnswer:
    if not key:
        raise ProviderConfigError("未配置 DEEPSEEK_API_KEY，请配置API密钥或选择浏览器采集")
    log_event("provider.started", operation="deepseek.chat")
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ],
        "stream": False
    }
    response = await client.post(
        "https://api.deepseek.com/chat/completions",
        headers=headers,
        json=payload
    )
    response.raise_for_status()
    try:
        result = response.json()
    except ValueError as error:
        raise ProviderResponseError("模型响应不是合法 JSON") from error
    answer = extract_answer(result)
    model = result.get("model")
    if model is not None and (
        not isinstance(model, str) or not model.strip() or len(model) > 200
    ):
        raise ProviderResponseError("模型响应的 model 字段无效")
    log_event("provider.succeeded", operation="deepseek.chat", status_code=response.status_code)
    return ProviderAnswer(answer=answer, provider="deepseek", model=model)
