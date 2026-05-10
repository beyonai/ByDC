"""基于 datacloud 示例的 Flask 服务。

接口说明：
1) POST /download-and-extract
   - 入参(JSON):
     {
       "file_url": "https://example.com/data.zip",
       "extract_to": "downloads/resource",   # 可选，默认 downloads/extracted
       "filename": "data.zip"                # 可选
     }
   - 功能：下载用户传入文件并自动解压（支持 zip / tar / tar.gz / tgz / tar.bz2 / tar.xz / gz）

2) POST /ask-stream
   - 入参(JSON):
     {
       "question": "必填",
       "object_codes": ["必填，数组"],
       "view_codes": null,
       "thread_id": "可选",
       "stream": true
     }
   - 功能：调用 OntologyAgent.ask
     - stream=false: 非流式，仅返回最终 answer
     - stream=true: SSE 流式返回除 answer 外的事件，包含 event 名和 OpenAI chunk 风格 data
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import logging.handlers
import os
import shutil
import tarfile
import time
import uuid
import zipfile
from pathlib import Path

from flask import Flask, Response, jsonify, request
import os
from dotenv import load_dotenv

load_dotenv()
# 打印所有环境变量（格式化输出，看得更清楚）
print("=== 所有已加载的环境变量 ===")
for key, value in sorted(os.environ.items()):
    print(f"{key} = {value}")
from datacloud_analysis.ontology_agent import (
    AnswerEvent,
    ErrorEvent,
    InterruptEvent,
    OntologyAgent,
    OntologyAgentConfig,
    StepEvent,
    ThinkingEvent,
)

app = Flask(__name__)
app.json.ensure_ascii = False

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_CONFIG_PATH = BASE_DIR / "by_datacloud_default_config.json"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "by_datacloud_flask_server.log"

_file_handler = logging.handlers.TimedRotatingFileHandler(
    LOG_PATH, when="midnight", backupCount=7, encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
request_audit_logger = logging.getLogger("by_datacloud_request_audit")
request_audit_logger.setLevel(logging.INFO)
request_audit_logger.propagate = False
if not request_audit_logger.handlers:
    request_audit_logger.addHandler(_file_handler)


def _read_runtime_config() -> dict:
    """实时读取配置文件，确保改配置后请求立即生效。"""
    if not DEFAULT_CONFIG_PATH.exists():
        return {}
    with open(DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _log_request(endpoint: str, payload: dict | None = None) -> None:
    headers_dict = dict(request.headers)
    request_audit_logger.info(
        "endpoint=%s headers=%s payload=%s",
        endpoint,
        json.dumps(headers_dict, ensure_ascii=False),
        json.dumps(payload or {}, ensure_ascii=False),
    )


def _resolve_resource_path(agent_conf: dict) -> Path:
    """解析 resource_path，默认使用下载解压目录。"""
    configured = agent_conf.get("resource_path")
    if configured:
        return Path(configured)
    return DOWNLOAD_DIR


def _build_agent(agent_conf: dict) -> OntologyAgent:
    """按配置构建 OntologyAgent。"""
    api_key = agent_conf.get("api_key", "")
    model = agent_conf.get("model", "kimi-k2.6")
    base_url = agent_conf.get("base_url", "https://api.moonshot.cn/v1")
    resource_path = str(_resolve_resource_path(agent_conf))
    temperature = float(agent_conf.get("temperature", 0.6))
    model_kwargs = agent_conf.get(
        "model_kwargs", {"extra_body": {"thinking": {"type": "disabled"}}}
    )

    config = OntologyAgentConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
        resource_path=resource_path,
        temperature=temperature,
        model_kwargs=model_kwargs
    )
    return OntologyAgent(config)


def _extract_archive(file_path: Path, extract_to: Path) -> Path:
    extract_to.mkdir(parents=True, exist_ok=True)
    lower_name = file_path.name.lower()

    if zipfile.is_zipfile(file_path):
        with zipfile.ZipFile(file_path, "r") as zf:
            zf.extractall(extract_to)
        return extract_to

    if tarfile.is_tarfile(file_path):
        with tarfile.open(file_path, "r:*") as tf:
            tf.extractall(extract_to)
        return extract_to

    if lower_name.endswith(".gz") and not lower_name.endswith((".tar.gz", ".tgz")):
        output_file = extract_to / file_path.stem
        with gzip.open(file_path, "rb") as src, open(output_file, "wb") as dst:
            shutil.copyfileobj(src, dst)
        return output_file

    raise ValueError("不支持的压缩格式，仅支持 zip/tar/tar.gz/tgz/tar.bz2/tar.xz/gz")


def _merge_move(src: Path, dst: Path) -> None:
    """将 src 合并移动到 dst，文件冲突时覆盖。"""
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        for child in src.iterdir():
            _merge_move(child, dst / child.name)
        src.rmdir()
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    src.rename(dst)


@app.route("/uploadOWL", methods=["POST"])
def upload_owl() -> Response:
    runtime_conf = _read_runtime_config()
    agent_conf = runtime_conf.get("ontology_agent", {})
    target_extract_dir = _resolve_resource_path(agent_conf)

    try:
        _log_request("/uploadOWL", {"content_type": request.content_type})
        # 仅支持 multipart/form-data 文件流上传（参考 api.py 的接收方式）
        if "file" not in request.files:
            return jsonify({"code": -1, "success": False, "message": "入参没有file"}), 400

        upload_file = request.files["file"]
        if not upload_file or not upload_file.filename:
            return jsonify({"code": -1, "success": False, "message": "文件名为空"}), 400

        filename = upload_file.filename
        save_path = DOWNLOAD_DIR / filename
        with open(save_path, "wb") as f:
            f.write(upload_file.stream.read())

        temp_extract_dir = DOWNLOAD_DIR / f".extract_{uuid.uuid4().hex}"
        extracted_path = Path(_extract_archive(save_path, temp_extract_dir))

        source_root = extracted_path
        if extracted_path.is_dir():
            top_items = list(extracted_path.iterdir())
            if len(top_items) == 1 and top_items[0].is_dir():
                source_root = top_items[0]

            for child in source_root.iterdir():
                _merge_move(child, target_extract_dir / child.name)
        else:
            _merge_move(source_root, target_extract_dir / source_root.name)

        shutil.rmtree(temp_extract_dir, ignore_errors=True)
        try:
            save_path.unlink(missing_ok=True)
        except Exception:
            pass
        return jsonify(
            {
                "code": 0,
                "success": True,
                "message": "上传并解压成功",
                "download_path": str(save_path),
                "extract_path": str(target_extract_dir),
            }
        )
    except Exception as e:
        return jsonify({"code": -1, "success": False, "message": f"处理失败: {e}"}), 500


def _sse_pack(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _sse_pack_with_event(event_name: str, payload: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_openai_chunk(
    chunk_id: str, model: str, content: str | None = None, role: str = "assistant"
) -> dict:
    delta = {"role": role}
    if content is not None:
        delta["content"] = content
    return {
        "id": chunk_id,
        "choices": [{"delta": delta, "index": 0}],
        "created": int(time.time()),
        "model": model,
        "object": "chat.completion.chunk",
    }


@app.route("/askOntology", methods=["POST"])
def ask_stream() -> Response:
    runtime_conf = _read_runtime_config()
    agent_conf = runtime_conf.get("ontology_agent", {})
    model_name = agent_conf.get("model", "kimi-k2.6")

    data = request.json or {}
    _log_request("/askOntology", data)
    question = data.get("question")
    object_codes = data.get("objectCodes") or data.get("object_codes")
    view_codes = data.get("viewCodes") or data.get("view_codes")
    session_id = data.get("sessionId") or data.get("session_id")

    thread_id = session_id or data.get("thread_id") or str(uuid.uuid4())
    stream = bool(data.get("stream", True))

    if not question:
        return jsonify({"code": -1, "success": False, "message": "缺少 question"}), 400
    if not isinstance(object_codes, list):
        return jsonify({"code": -1, "success": False, "message": "object_codes 必须是数组"}), 400

    chunk_id = f"chatcmpl-{thread_id}"

    if not stream:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        final_answer = ""
        try:
            agent = _build_agent(agent_conf)
            async_gen = agent.ask(
                question=question,
                object_codes=object_codes,
                view_codes=view_codes,
                thread_id=thread_id,
            )

            while True:
                try:
                    event = loop.run_until_complete(async_gen.__anext__())
                except StopAsyncIteration:
                    break
                if isinstance(event, AnswerEvent):
                    final_answer = event.content or final_answer

            result = {
                "id": chunk_id,
                "created": int(time.time()),
                "model": model_name,
                "object": "chat.completion",
                "answer": final_answer,
            }
            return Response(
                json.dumps(result, ensure_ascii=False),
                mimetype="application/json",
            )
        except Exception as e:
            return jsonify({"code": -1, "success": False, "message": str(e)}), 500
        finally:
            loop.close()

    def event_stream():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            agent = _build_agent(agent_conf)
            async_gen = agent.ask(
                question=question,
                object_codes=object_codes,
                view_codes=view_codes,
                thread_id=thread_id,
            )

            while True:
                try:
                    event = loop.run_until_complete(async_gen.__anext__())
                except StopAsyncIteration:
                    break

                if isinstance(event, ThinkingEvent):
                    payload = _build_openai_chunk(chunk_id, model_name, event.content)
                    yield _sse_pack_with_event("thinking", payload)
                elif isinstance(event, StepEvent):
                    payload = _build_openai_chunk(chunk_id, model_name, event.title)
                    yield _sse_pack_with_event("step", payload)
                elif isinstance(event, AnswerEvent):
                    # 按需求：stream=true 时，返回除 answer 外的全部结果
                    continue
                elif isinstance(event, ErrorEvent):
                    payload = _build_openai_chunk(chunk_id, model_name, event.message)
                    yield _sse_pack_with_event("error", payload)
                elif isinstance(event, InterruptEvent):
                    payload = _build_openai_chunk(chunk_id, model_name, "意外中断")
                    yield _sse_pack_with_event("interrupt", payload)
                else:
                    payload = _build_openai_chunk(chunk_id, model_name, str(event))
                    yield _sse_pack_with_event("unknown", payload)

            yield "event: done\ndata: [DONE]\n\n"
        except Exception as e:
            payload = _build_openai_chunk(chunk_id, model_name, str(e))
            yield _sse_pack_with_event("hermes.error", payload)
        finally:
            loop.close()

    return Response(event_stream(), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5090)
