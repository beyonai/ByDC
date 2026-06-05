"""OpenTelemetry 初始化模块（Superlog 接入）。

通过 SUPERLOG_PUBLIC_TOKEN 环境变量控制开关。
未配置时跳过，不影响正常运行。

使用方式：在应用启动时调用一次 init_otel()，之后通过标准 OTel API 埋点。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

SUPERLOG_ENDPOINT = "https://intake.superlog.sh"

_initialized: bool = False


def _superlog_headers(token: str) -> dict[str, str]:
    return {"x-api-key": token}


def init_otel() -> bool:
    """初始化 OpenTelemetry，将 traces/logs/metrics 发送到 Superlog。

    注意：Superlog 集成当前已停用（SUPERLOG_PUBLIC_TOKEN 未配置）。
    若需切换到其他 OTLP 后端，在此修改 endpoint 和认证方式即可。

    Returns:
        True 表示初始化成功，False 表示跳过（未配置 token 或依赖缺失）。
    """
    global _initialized  # noqa: PLW0603
    if _initialized:
        return True

    token = os.getenv("SUPERLOG_PUBLIC_TOKEN")
    if not token:
        logger.debug("otel: SUPERLOG_PUBLIC_TOKEN 未设置，跳过 OpenTelemetry 初始化")
        return False

    try:
        from opentelemetry import metrics, trace  # noqa: PLC0415
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (  # noqa: PLC0415
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider  # noqa: PLC0415
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader  # noqa: PLC0415
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource  # noqa: PLC0415
        from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

        headers = _superlog_headers(token)
        resource = Resource.create(
            {
                SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "by-datacloud"),
                "deployment.environment.name": os.getenv("DEPLOYMENT_ENV", "development"),
            }
        )

        # --- Traces ---
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=f"{SUPERLOG_ENDPOINT}/v1/traces",
                    headers=headers,
                )
            )
        )
        trace.set_tracer_provider(tracer_provider)

        # --- Metrics ---
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(
                endpoint=f"{SUPERLOG_ENDPOINT}/v1/metrics",
                headers=headers,
            )
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)

        _initialized = True
        logger.info("otel: OpenTelemetry 初始化成功，数据发送至 Superlog")
        return True

    except ImportError:
        logger.warning(
            "opentelemetry 依赖未安装，已跳过。可通过 `uv add opentelemetry-sdk "
            "opentelemetry-exporter-otlp-proto-http` 启用。"
        )
        return False
    except Exception:
        logger.warning("OpenTelemetry 初始化失败，已跳过", exc_info=True)
        return False
