"""
OpenTelemetry instrumentation for all OTA agents.

WHY this module exists: Every AI agent call must be observable — we need
to know what input the model received, what it returned, how long it took,
and how much it cost in tokens. This module provides two things:

  1. init_agent_telemetry() — called once at app startup in main.py.
     Wires OpenTelemetry traces to Azure Application Insights so every
     agent span appears in the Foundry Observability portal and Azure Monitor.

  2. invoke_with_tracing() — async context manager used to wrap every
     individual agent call. Emits a span with OTA-specific attributes
     (agent name, stage, trade key, verdict, token counts, latency).

HOW IT WORKS:
  - OpenTelemetry is the open standard for distributed tracing.
  - azure-monitor-opentelemetry is Microsoft's SDK that sends OTel spans
    to Application Insights without any custom exporters.
  - Each span gets custom ota.* attributes on top of the standard GenAI
    attributes, so we can filter/query by agent, stage, or trade key.

SENSITIVE DATA POLICY:
  - Full prompt text is NEVER logged to telemetry in production.
  - Only metadata (tokens, latency, verdict, trade_key) is in spans.
  - Full prompt/response text goes to agent_run_log in Azure SQL only.
"""

import os
import time
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

# Tracer — module-level singleton, initialized after configure_azure_monitor()
_tracer = None


def init_agent_telemetry(connection_string: str | None) -> None:
    """
    Wire OpenTelemetry to Azure Application Insights.

    Called once at app startup in main.py after SecretsManager is ready.
    If no connection string is available (local dev without Key Vault),
    this is a no-op — agents still work, they just don't emit traces.

    WHY not raise on missing connection string: Local dev shouldn't require
    Application Insights. The app should degrade gracefully.
    """
    global _tracer

    if not connection_string:
        logger.warning(
            "telemetry: No APPLICATIONINSIGHTS_CONNECTION_STRING — "
            "agent traces will not be sent to Application Insights"
        )
        _tracer = None
        return

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry import trace

        configure_azure_monitor(
            connection_string=connection_string,
            enable_live_metrics=True,
        )
        _tracer = trace.get_tracer("ota.agents")
        logger.info("telemetry: OpenTelemetry wired to Application Insights")
    except Exception as e:
        logger.warning(f"telemetry: OpenTelemetry setup failed ({e}) — traces disabled")
        _tracer = None


@asynccontextmanager
async def invoke_with_tracing(
    agent_name: str,
    stage: str,
    trade_key: str | None = None,
    symbol: str | None = None,
    session_id: str | None = None,
    prompt_version: str = "unversioned",
) -> AsyncGenerator[dict, None]:
    """
    Async context manager that wraps one agent invocation in an OTel span.

    Usage:
        async with invoke_with_tracing("claude-trade-agent", "deep_dive",
                                       trade_key="SPY:440/445:2026-04-17",
                                       symbol="SPY") as span_ctx:
            result = await call_model(...)
            span_ctx["verdict"] = result["verdict"]
            span_ctx["input_tokens"] = result["usage"]["input_tokens"]
            span_ctx["output_tokens"] = result["usage"]["output_tokens"]

    The caller sets keys on span_ctx during the call; this wrapper emits
    them as span attributes after the call completes.

    If tracing is not configured, this is a transparent pass-through —
    the body still executes normally, just without a span.
    """
    span_ctx: dict = {
        "verdict": None,
        "input_tokens": None,
        "output_tokens": None,
        "otel_trace_id": None,
    }

    if _tracer is None:
        # Tracing not configured — run body without a span
        yield span_ctx
        return

    from opentelemetry import trace
    from opentelemetry.trace import SpanKind, StatusCode

    start_time = time.monotonic()

    with _tracer.start_as_current_span(
        f"{agent_name}/{stage}",
        kind=SpanKind.INTERNAL,
    ) as span:
        # Capture trace ID for linking to agent_run_log
        trace_id = span.get_span_context().trace_id
        span_ctx["otel_trace_id"] = format(trace_id, "032x") if trace_id else None

        # Standard OTA span attributes set at the start
        span.set_attribute("ota.agent.name", agent_name)
        span.set_attribute("ota.agent.stage", stage)
        span.set_attribute("ota.prompt.version", prompt_version)
        if trade_key:
            span.set_attribute("ota.trade.key", trade_key)
        if symbol:
            span.set_attribute("ota.trade.symbol", symbol)
        if session_id:
            span.set_attribute("ota.session.id", session_id)

        try:
            yield span_ctx

            # After the body runs, emit outcome attributes
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            span.set_attribute("ota.latency_ms", elapsed_ms)

            if span_ctx.get("verdict"):
                span.set_attribute("ota.verdict", span_ctx["verdict"])
            if span_ctx.get("input_tokens") is not None:
                span.set_attribute("gen_ai.usage.input_tokens", span_ctx["input_tokens"])
            if span_ctx.get("output_tokens") is not None:
                span.set_attribute("gen_ai.usage.output_tokens", span_ctx["output_tokens"])

        except Exception as e:
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, str(e))
            raise
