"""后台执行权的时间配置，不与 HTTP 超时或登录令牌混用。"""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class LeaseSettings:
    seconds: int = 60
    heartbeat_seconds: int = 15
    recovery_seconds: int = 15


# 启动和执行时校验配置，续期间隔必须明显短于到期时间。
def get_lease_settings() -> LeaseSettings:
    settings = LeaseSettings(
        seconds=int(os.getenv("GEO_JOB_LEASE_SECONDS", "60")),
        heartbeat_seconds=int(os.getenv("GEO_JOB_HEARTBEAT_SECONDS", "15")),
        recovery_seconds=int(os.getenv("GEO_JOB_RECOVERY_SECONDS", "15")),
    )
    if min(settings.seconds, settings.heartbeat_seconds, settings.recovery_seconds) <= 0:
        raise ValueError("任务租约配置必须为正整数")
    if settings.heartbeat_seconds * 2 >= settings.seconds:
        raise ValueError("心跳间隔必须小于租约有效期的一半")
    return settings
