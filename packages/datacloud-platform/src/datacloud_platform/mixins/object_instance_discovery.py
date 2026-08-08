"""非结构化对象实例发现编排（ObjectInstanceDiscoveryMixin）。

流程：参数校验 → 输入实例定位并读取知识库文件（get_document_content_by_term_id）
→ LLM 抽取（优先类型列表 + 允许自动发现新类型）→ 词典锚定（快路命中 + 反查兜底）
→ 冲突候选裁决（同名多候选判歧义、子串重叠判同义）→ 新实例创建（write action /
自动发现直写）→ term_id 强校验 → 文件登记 → 「提及」关系（源→目标，单向幂等）
→ 返回结果。

无降级：任何异常直接上抛，由 RPC 层统一映射为错误码。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import asdict, dataclass
from functools import partial
from typing import Any, Protocol

from anyio import to_thread
from datacloud_data_sdk.context import get_current_context
from datacloud_knowledge.intent.llm_utils import (
    build_llm,
    stream_invoke_with_thinking,
)

from datacloud_platform.mixins.document import (
    _build_object_file_status,
    build_processing_labels,
)
from datacloud_platform.models.document import (
    DocumentContentResult,
    DocumentEnrichObjectScope,
    DocumentObjectItem,
    DocumentProcessingStatus,
)
from datacloud_platform.models.shared import (
    ObjectInstanceDiscoveryHit,
    ObjectInstanceDiscoveryResult,
    ObjectInstanceWriteMissingTermIdError,
)
from datacloud_platform.services.object_action import (
    invoke_object_write_action,
    unwrap_action_result,
)

logger = logging.getLogger(__name__)


def _current_session_id() -> str:
    """从全局请求上下文获取会话 ID（由 server middleware 注入 InvocationContext）。

    无请求上下文（后台任务/单测直调）时返回空串，不抛异常。
    """
    try:
        # str() 显式收窄：跨包边界（datacloud-data 未纳入 mypy 解析）时为 Any
        return str(get_current_context().session_id)
    except Exception:
        return ""


_PENDING_LABELS: dict[str, Any] = {
    "dc_status": "待整理",
    "dc_failure_reason": None,
    "dc_failure_count": 0,
}

# 锚定反查单次检索条数上限（词面相等/子串重叠判定所需的候选窗口）
_ANCHOR_SEARCH_TOP_K = 50

# LLM 抽取参数：长文截断上限与 JSON 重试退避
_MAX_EXTRACT_CHARS = (
    16_000  # 长文截断单次上限（document_enrich _MAX_ORIGINAL_CHARS 同值）
)
_MAX_JSON_RETRIES = 3  # 非法 JSON 重试次数（≤3 次退避）
_JSON_RETRY_BACKOFF_SECONDS = 0.5  # 重试退避基数（attempt * 基数）
_AUTO_DISCOVERED_CODE = "AUTO_DISCOVERED"  # LLM 自动发现类型（禁用 "UNKNOWN"）
# 抽取类型不在调用方枚举内时使用的兜底类型（原始类型名保留在 ext_attrs.raw_type）
_AUTO_DISCOVERED_TYPE_NAME = "自动发现类型"

_LEADING_THINKING_PATTERN = re.compile(
    r"\A\s*(?:<(?:think|thinking|analysis)>.*?</(?:think|thinking|analysis)>\s*)+",
    re.DOTALL | re.IGNORECASE,
)


@dataclass(frozen=True)
class _AnchorResult:
    """词典锚定结果分发（快路命中 + 反查兜底后的四桶归类）。

    Attributes:
        existing: 唯一词面相等命中 → 已有实例候选行（is_new=False，含 evidence）。
        ambiguity: 词面相等命中 ≥2 term → 同名多候选（进歧义裁决）。
        synonym: 与已有 term 子串重叠（非相等）→ 同义候选（进同义裁决）。
        unanchored: 未锚定 mention 原样返回（走新实例创建）。
    """

    existing: list[dict[str, Any]]
    ambiguity: list[dict[str, Any]]
    synonym: list[dict[str, Any]]
    unanchored: list[dict[str, Any]]


# ── 词典缓存单例────────────────────────────────────────────────────────
# 归属：编排侧（本模块）模块级单例，读取经 ``list_vocabulary`` 协议；
# 缓存只做「候选判定」，不做「最终锚定」——真命中必须经反查拿 term_id。
# 缓存旧（增删词未刷新）最多损失快路（多走一次 DB 查询），不产生错误锚定。
_cached_vocabulary: frozenset[str] | None = None


def invalidate_vocabulary_cache() -> None:
    """显式失效词典缓存：发现管道创建 term / 回填词后调用。

    置空缓存，下次 discover 重新经 ``list_vocabulary()`` 全量加载 → 飞轮实时。
    """
    global _cached_vocabulary
    _cached_vocabulary = None


class _ObjectInstanceDiscoveryPlatform(Protocol):
    """ObjectInstanceDiscoveryMixin 所依赖的 Platform 最小能力协议。"""

    async def get_document_content_by_term_id(
        self, base_id: str, *, term_id: str
    ) -> DocumentContentResult: ...
    def list_term_relations(self, base_id: str, **kwargs: Any) -> dict[str, Any]: ...
    def create_term_relation(
        self, base_id: str, *, relation: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def save_or_update_object_files(
        self, base_id: str, *, object_files: list[dict[str, Any]]
    ) -> Any: ...
    def list_vocabulary(self, base_id: str) -> list[str]: ...
    def search_terms(self, base_id: str, **kwargs: Any) -> Any: ...
    def search_terms_batch(self, base_id: str, **kwargs: Any) -> dict[str, Any]: ...
    def search_terms_exact(self, base_id: str, **kwargs: Any) -> Any: ...
    def list_term_names(self, base_id: str, **kwargs: Any) -> list[dict[str, Any]]: ...
    def get_term_type(
        self, base_id: str, *, library_id: str, type_code: str
    ) -> dict[str, Any] | None: ...
    def batch_create_vocabulary(self, base_id: str, *, words: list[str]) -> None: ...
    def ensure_term_type(
        self, *, base_id: str, type_code: str, type_name: str
    ) -> None: ...
    def create_term(self, base_id: str, *, term: dict[str, Any]) -> dict[str, Any]: ...
    def create_term_knowledge(
        self, base_id: str, *, knowledge: dict[str, Any]
    ) -> dict[str, Any]: ...
    def create_term_name(
        self, base_id: str, *, name: dict[str, Any]
    ) -> dict[str, Any]: ...
    def get_term_detail(
        self, base_id: str, *, library_id: str, term_id: str
    ) -> dict[str, Any] | None: ...
    def update_term_co_occurrence(
        self, base_id: str, *, term_id: str, patch: dict[str, int]
    ) -> None: ...


class ObjectInstanceDiscoveryMixin:
    """非结构化对象实例发现编排（与 DocumentMixin 平级，不继承）。

    通过 ``_ObjectInstanceDiscoveryPlatform`` 声明对平台的最小能力依赖。
    """

    async def discover_object_instances_unstructured(
        self: Any,
        base_id: str,
        *,
        instance_id: str,
        object_codes: list[str],
    ) -> ObjectInstanceDiscoveryResult:
        """从输入实例的知识库文件中发现对象实例。

        Args:
            base_id: 本体库/系统空间标识。
            instance_id: 输入实例的 term_id。
            object_codes: 非结构化对象类型编码列表（已有实例匹配范围 + 新实例候选类型）。

        Returns:
            发现结果信封；已有实例在前、新实例在后，每项含 is_new 标记。

        Raises:
            ValueError: 入参非法（instance_id 为空 / object_codes 缺失）。
            KeyError: 输入实例不存在。
        """
        # 参数校验
        if not instance_id.strip():
            raise ValueError("instance_id is required")
        if not object_codes:
            raise ValueError("object_codes must be a non-empty list")
        if not all(str(code).strip() for code in object_codes):
            raise ValueError("object_codes must not contain blank values")

        # 输入实例定位 + 读文件（异常原样上抛，无降级）
        document = await self.get_document_content_by_term_id(
            base_id, term_id=instance_id
        )

        # LLM 抽取 → mention 列表（实现编排 抽取→锚定，对外顺序不变）
        mentions = await self._discover_new_object_instances(
            base_id, content=document.content, object_codes=object_codes
        )

        # 词典锚定（快路命中 + 反查兜底）→ 结果分发
        anchor = self._discover_existing_object_instances(
            base_id, mentions=mentions, object_codes=object_codes
        )

        # 全链路串联：已有在前、新在后；未锚定逐项 创建 → 强校验 → 登记 → 提及关系
        items: list[ObjectInstanceDiscoveryHit] = [
            _build_existing_hit(row) for row in anchor.existing
        ]
        for candidate in anchor.unanchored:
            items.append(
                await self._create_new_instance_flow(
                    base_id=base_id,
                    source_term_id=instance_id,
                    candidate=candidate,
                )
            )
        # 同步裁决：仅与库冲突候选（同名多候选→歧义、子串重叠→同义）；
        # 同义 → 写 TermName 别名不建实例；歧义 → 独立新实例；无冲突 → 直通不调裁决
        alias_targets: list[str] = []
        items.extend(
            await self._adjudicate_candidates(
                base_id=base_id,
                ambiguity=anchor.ambiguity,
                synonym=anchor.synonym,
                source_term_id=instance_id,
                alias_targets=alias_targets,
            )
        )
        # 共现存储：同文档实例两两 +1（含同义归并 canonical 伙伴集）；
        # 使用过滤前全量 items——AUTO_DISCOVERED 兜底实例仍参与共现（词表飞轮）
        self._update_document_co_occurrence(
            base_id, [h.instance_id for h in items] + alias_targets
        )
        # 返回结果过滤（业务语义）：
        # 1) AUTO_DISCOVERED 兜底类型实例仍入库（词表飞轮/共现用），但不作为发现结果返回；
        # 2) 输入实例自身不返回（如 object_codes 含 Document 时 LLM 抽出文档名锚定回输入实例）。
        items = [
            hit
            for hit in items
            if hit.object_code != _AUTO_DISCOVERED_CODE
            and hit.instance_id != instance_id
        ]
        return ObjectInstanceDiscoveryResult(items=items)

    def _vocabulary_words(
        self: _ObjectInstanceDiscoveryPlatform, base_id: str
    ) -> frozenset[str]:
        """惰性加载词典缓存（单例）。

        全量 term_vocabulary → frozenset，O(1) 命中判定。只做候选判定，
        不做最终锚定（真命中必须经反查拿 term_id）。失效经
        :func:`invalidate_vocabulary_cache` 显式触发，下次访问重载。

        Args:
            base_id: 本体库/系统空间标识（透传 list_vocabulary 协议）。

        Returns:
            词典词集合（frozenset）。
        """
        global _cached_vocabulary
        if _cached_vocabulary is None:
            words = self.list_vocabulary(base_id)
            _cached_vocabulary = frozenset(words)
        return _cached_vocabulary

    async def _create_new_instance_flow(
        self: Any,
        *,
        base_id: str,
        source_term_id: str,
        candidate: dict[str, Any],
    ) -> ObjectInstanceDiscoveryHit:
        """新实例创建链路：创建 → 强校验 → 登记 → 提及关系。

        Args:
            base_id: 本体库/系统空间标识。
            source_term_id: 输入实例 term_id（提及关系源）。
            candidate: 新实例候选 ``{"term_name", "object_code", "evidence"}``。

        Returns:
            新实例发现结果项（is_new=True，relation_name="提及"）。

        Raises:
            ValueError: 候选缺 object_code/term_name。
            ObjectInstanceWriteMissingTermIdError: write 响应缺 term_id。
        """
        object_code = str(candidate["object_code"]).strip()
        term_name = str(candidate["term_name"]).strip()
        if not object_code or not term_name:
            raise ValueError("discovered candidate must have object_code and term_name")
        evidence = candidate.get("evidence")
        evidence_text = str(evidence) if evidence is not None else None

        term_id = await self._create_discovered_instance(
            base_id=base_id,
            object_code=object_code,
            term_name=term_name,
            raw_type=str(candidate["raw_type"])
            if candidate.get("raw_type") is not None
            else None,
        )
        await self._register_object_file(
            base_id=base_id,
            object_code=object_code,
            term_name=term_name,
            term_id=term_id,
            action_result={"records": [{"term_id": term_id}]},
        )
        self._establish_mention_relation(
            base_id=base_id,
            source_term_id=source_term_id,
            target_term_id=term_id,
        )
        return ObjectInstanceDiscoveryHit(
            instance_id=term_id,
            instance_code=term_name,
            instance_name=term_name,
            object_code=object_code,
            file_name=f"/{object_code}/{term_name}.md",
            kb_resource_id=None,
            kb_id=None,
            is_new=True,
            evidence=evidence_text,
        )

    async def _create_discovered_instance(
        self: Any,
        *,
        base_id: str,
        object_code: str,
        term_name: str,
        raw_type: str | None = None,
    ) -> str:
        """新实例创建 + term_id 强校验。

        两条通道：

        - 常规类型：经 ``invoke_object_write_action``（services/object_action.py）
          写入知识库文件（write_<object_code> action），对响应做 term_id 强校验。
        - ``AUTO_DISCOVERED``：方案 (a) 兜底直写——无 ontology 对象，跳过
          action 管道，直建 term + knowledge（``ext_attrs.raw_type`` 保留 LLM
          原始类型名，``labels.dc_status`` 待整理），登记/关系照旧。

        Args:
            base_id: 本体库/系统空间标识。
            object_code: 新实例对象类型编码。
            term_name: 新实例名称。
            raw_type: LLM 原始类型名（仅 AUTO_DISCOVERED 分支使用）。

        Returns:
            强校验非空的 term_id。

        Raises:
            ObjectInstanceWriteMissingTermIdError: write 响应缺 term_id。
        """
        if object_code == _AUTO_DISCOVERED_CODE:
            term_id: str = self._create_auto_discovered_instance(
                base_id=base_id,
                term_name=term_name,
                raw_type=raw_type,
            )
            return term_id
        labels = build_processing_labels(
            initial_status=DocumentProcessingStatus.PENDING_ORGANIZATION,
            labels=_PENDING_LABELS,
        )
        term_name = term_name.strip()
        content = f"# {term_name}\n\n{term_name}对象实例文档。"
        source_path = f"/{object_code}/{term_name}.md"
        result = await invoke_object_write_action(
            platform=self,
            base_id=base_id,
            object_code=object_code,
            content=content,
            labels=labels,
            file_description=f"{term_name}对象实例文档",
            source_path=source_path,
        )
        term_id = _extract_written_term_id(result)
        # 新实例落库 → 词表已更新 → 飞轮实时（下次 discover 重载词典）
        invalidate_vocabulary_cache()
        return term_id

    def _create_auto_discovered_instance(
        self: _ObjectInstanceDiscoveryPlatform,
        *,
        base_id: str,
        term_name: str,
        raw_type: str | None,
    ) -> str:
        """方案 (a) 兜底直写：AUTO_DISCOVERED 类型实例直接入库。

        背景：常规类型现走 ``invoke_object_write_action`` →
        ``loader.get_object(object_code)`` 对无 ontology 对象的类型抛
        ``ObjectNotFoundError``（未映射 → 500）。AUTO_DISCOVERED 无 ontology
        对象 → 改走 ``create_term``（TermBackend → insert_term）直建 term +
        ``create_term_knowledge``（insert_term_knowledge），跳过 action 管道。

        流程：
        1. ``ensure_term_type`` 幂等落地 TermType 预置行（is_builtin=true）
        2. ``create_term`` 直写（term_type_code=AUTO_DISCOVERED、
           ``ext_attrs.raw_type`` 保留原始类型名、``labels.dc_status=待整理``）
        3. ``create_term_knowledge`` 补充知识
        4. 缓存失效（飞轮实时）

        Args:
            base_id: 本体库/系统空间标识。
            term_name: 新实例名称。
            raw_type: LLM 原始类型名（可为 None）。

        Returns:
            create_term 响应中的 term_id（强校验非空）。

        Raises:
            ObjectInstanceWriteMissingTermIdError: create_term 响应缺 term_id。
        """
        term_name = term_name.strip()
        # TermType 预置行（幂等：重复执行不报错，is_builtin 由 knowledge 层保障）
        self.ensure_term_type(
            base_id=base_id,
            type_code=_AUTO_DISCOVERED_CODE,
            type_name=_AUTO_DISCOVERED_TYPE_NAME,
        )
        labels = build_processing_labels(
            initial_status=DocumentProcessingStatus.PENDING_ORGANIZATION,
            labels=_PENDING_LABELS,
        )
        ext_attrs: dict[str, Any] = {}
        if raw_type:
            ext_attrs["raw_type"] = raw_type
        result = self.create_term(
            base_id,
            term={
                "term_name": term_name,
                "term_type_code": _AUTO_DISCOVERED_CODE,
                "labels": labels,
                "ext_attrs": ext_attrs,
            },
        )
        term_id = _extract_imported_term_id(result)
        self.create_term_knowledge(
            base_id,
            knowledge={
                "termId": term_id,
                "descSummary": f"自动发现对象实例：{term_name}",
                "desc": (
                    f"{term_name} 为 LLM 自动发现的对象实例"
                    f"（原始类型：{raw_type or '未知'}）。"
                ),
            },
        )
        # 直写落库 → 词表已更新 → 飞轮实时
        invalidate_vocabulary_cache()
        return term_id

    async def _adjudicate_candidates(
        self: Any,
        *,
        base_id: str,
        ambiguity: list[dict[str, Any]],
        synonym: list[dict[str, Any]],
        source_term_id: str,
        alias_targets: list[str] | None = None,
    ) -> list[ObjectInstanceDiscoveryHit]:
        """冲突候选同步裁决：同名多候选判歧义、子串重叠判同义。

        候选范围严格收窄：
        - 同名多候选（词面相等 ≥2 term）→ 歧义判断
        - 子串重叠（非相等）→ 同义判断
        - 干净命中 / 新实例间两两 → **不裁决**

        结果（temp=0 一票，带上下文）：
        - ``same=true`` / ``same_entity=true`` → ``create_term_name`` 归并别名
          到主 term（触发器自动进词典，随后缓存失效）；**不建新实例**
        - ``false`` → 独立新实例（复用 ``_create_new_instance_flow``；类型规则
          类型规则：mention 自带可定类型 → 该类型，确定不了 → AUTO_DISCOVERED）

        Args:
            base_id: 本体库/系统空间标识。
            ambiguity: 歧义候选列表（同名多候选）。
            synonym: 同义候选列表（子串重叠）。
            source_term_id: 输入实例 term_id（新实例提及关系源）。
            alias_targets: 可选 out 参数——归并的 canonical term_id 收集
                （共现：别名 mention 计入 canonical 伙伴集）。

        Returns:
            新实例发现结果项（别名归并不产出 hit）。
        """
        hits: list[ObjectInstanceDiscoveryHit] = []
        for candidate in synonym:
            mention = str(candidate["mention"])
            term = candidate["term"]
            verdict = await self._invoke_synonym_judge(base_id, candidate=candidate)
            if verdict.get("same") is True:
                canonical = str(
                    verdict.get("canonical") or term.get("term_id") or ""
                ).strip()
                if canonical:
                    self._write_alias(
                        base_id=base_id, term_id=canonical, name_text=mention
                    )
                    if alias_targets is not None:
                        alias_targets.append(canonical)
            else:
                hits.append(
                    await self._create_new_instance_flow(
                        base_id=base_id,
                        source_term_id=source_term_id,
                        candidate={
                            "term_name": mention,
                            "object_code": _mention_object_code(candidate),
                            "evidence": candidate.get("evidence"),
                            "raw_type": candidate.get("raw_type"),
                        },
                    )
                )
        for candidate in ambiguity:
            mention = str(candidate["mention"])
            terms = candidate["terms"]
            verdict = await self._invoke_ambiguity_judge(base_id, candidate=candidate)
            if verdict.get("same_entity") is True:
                canonical = _pick_canonical_term_id(
                    terms, verdict.get("entity_names") or []
                )
                if canonical:
                    self._write_alias(
                        base_id=base_id, term_id=canonical, name_text=mention
                    )
                    if alias_targets is not None:
                        alias_targets.append(canonical)
            else:
                hits.append(
                    await self._create_new_instance_flow(
                        base_id=base_id,
                        source_term_id=source_term_id,
                        candidate={
                            "term_name": mention,
                            "object_code": _mention_object_code(candidate),
                            "evidence": candidate.get("evidence"),
                            "raw_type": candidate.get("raw_type"),
                        },
                    )
                )
        return hits

    async def _invoke_synonym_judge(
        self: Any,
        base_id: str,
        *,
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        """同义裁决（judge_synonym 形态）。

        实体A=mention（含 evidence 上下文）、实体B=已有 term；生产增强：
        防御式读取 term 侧 co_occurrence 伙伴集（共现未写入 → 空 → 不带段）。

        Args:
            base_id: 本体库/系统空间标识。
            candidate: 同义候选 ``{"mention", "term", ...}``。

        Returns:
            裁决对象 ``{"same": bool, "canonical": str}``。
        """
        mention = str(candidate["mention"])
        term = candidate["term"]
        evidence = candidate.get("evidence")
        mention_context = str(evidence) if evidence is not None else ""
        overlap = self._co_occurrence_overlap(base_id, [str(term.get("term_id") or "")])
        messages = _build_synonym_prompt(
            mention=mention,
            mention_context=mention_context,
            term_row=term,
            partner_overlap=overlap,
        )
        verdict: dict[str, Any] = await self._invoke_judge_llm_verified(messages)
        return verdict

    async def _invoke_ambiguity_judge(
        self: Any,
        base_id: str,
        *,
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        """歧义裁决（judge_ambiguity 形态）。

        同词面不同 term 各自上下文（term_name + 类型 + 文件），防御式附
        co_occurrence 伙伴集交集。

        Args:
            base_id: 本体库/系统空间标识。
            candidate: 歧义候选 ``{"mention", "terms", ...}``。

        Returns:
            裁决对象 ``{"same_entity": bool, "entity_names": [...]}``。
        """
        mention = str(candidate["mention"])
        terms = candidate["terms"]
        contexts = [
            f"{_row_term_name(row)}（类型: {row.get('term_type_code')}，"
            f"文件: {row.get('file_name') or '无'}）"
            for row in terms
        ]
        overlap = self._co_occurrence_overlap(
            base_id, [str(row.get("term_id") or "") for row in terms]
        )
        messages = _build_ambiguity_prompt(
            mention=mention, term_contexts=contexts, partner_overlap=overlap
        )
        verdict: dict[str, Any] = await self._invoke_judge_llm_verified(messages)
        return verdict

    async def _invoke_judge_llm_verified(
        self: Any, messages: list[dict[str, str]]
    ) -> dict[str, Any]:
        """裁决 LLM 调用：严格 JSON 对象解析 + <think> 剥离 + ≤3 次重试退避。

        Args:
            messages: prompt 消息列表。

        Returns:
            解析后的裁决对象（dict）。

        Raises:
            RuntimeError: 重试后仍非合法 JSON 对象（无降级）。
        """
        last_error = ""
        for attempt in range(_MAX_JSON_RETRIES):
            if attempt > 0:
                await asyncio.sleep(_JSON_RETRY_BACKOFF_SECONDS * attempt)
                retry_messages = messages + [
                    {
                        "role": "user",
                        "content": (
                            f"上次输出不是合法 JSON（{last_error}）。"
                            "请重新只输出严格 JSON 对象，不要任何解释。"
                        ),
                    }
                ]
            else:
                retry_messages = messages
            raw = await self._invoke_judge_llm(retry_messages)
            text = _llm_response_text(raw)
            parsed = _parse_judge_json(text)
            if parsed is not None:
                return parsed
            last_error = text[:200] if text else "空输出"
        raise RuntimeError(
            f"裁决 LLM 输出非法 JSON（重试 {_MAX_JSON_RETRIES} 次仍失败）: {last_error}"
        )

    async def _invoke_judge_llm(self: Any, messages: list[dict[str, str]]) -> Any:
        """调用裁决 LLM（build_llm + stream_invoke_with_thinking，temp=0 环境默认）。

        经 ``anyio.to_thread.run_sync`` 移出事件循环线程。
        """
        return await to_thread.run_sync(partial(_judge_llm_sync, messages=messages))

    def _write_alias(
        self: _ObjectInstanceDiscoveryPlatform,
        *,
        base_id: str,
        term_id: str,
        name_text: str,
    ) -> None:
        """同义/歧义归并落库：create_term_name 写别名 + 缓存失效。

        幂等（业务语义）：重复发现同一文档时同义裁决可能再次归并同一别名，
        ``_base_create_term_name`` 无查重直接 INSERT，会撞 ``uq_term_name_scope``
        唯一约束（(term_id, name_text, search_scope)）→ 整个发现任务 500。
        写前按 (term_id, name_text) 精确查重：``list_term_names`` 的 name_text
        参数为 ilike 模糊匹配，精确判定须在 Python 侧完成；仅对空 search_scope
        行去重（与本方法写入的 ``searchScope: {}`` 三元组一致），已存在 → 跳过。
        别名经触发器 ``trg_term_name_vocab`` 自动投影进词典 → 下次锚定可命中。
        search_scope 通用作用域（user 级留空）。
        """
        existing = self.list_term_names(base_id, term_id=term_id)
        if any(
            str(row.get("name_text")) == name_text and not row.get("search_scope")
            for row in existing
        ):
            logger.debug(
                "同义别名已存在，跳过写入: term_id=%s name_text=%s",
                term_id,
                name_text,
            )
            return
        self.create_term_name(
            base_id,
            name={
                "termId": term_id,
                "nameText": name_text,
                "searchScope": {},
            },
        )
        invalidate_vocabulary_cache()

    def _co_occurrence_overlap(
        self: _ObjectInstanceDiscoveryPlatform,
        base_id: str,
        term_ids: list[str],
    ) -> str | None:
        """防御式读取：term_tags.co_occurrence 伙伴集交集（裁决语境信号）。

        经 ``get_term_detail`` 读各 term 的 ``term_tags.co_occurrence``
        （``{partner_term_id: count}``）；求伙伴集交集。共现未写入时伙伴集
        为空 → 返回 None → prompt 不带共现段，不阻塞。

        Args:
            base_id: 本体库/系统空间标识。
            term_ids: 参与交集计算的 term_id 列表（去空）。

        Returns:
            共现语境段文本；无交集/无数据时 None。
        """
        partner_sets: list[set[str]] = []
        for term_id in term_ids:
            if not term_id:
                continue
            detail = self.get_term_detail(base_id, library_id=base_id, term_id=term_id)
            if detail is None:
                continue
            # 兼容 dict（mock/适配器）与 TermDetail dataclass（真实后端）
            if isinstance(detail, dict):
                tags = detail.get("term_tags") or {}
            else:
                tags = getattr(detail, "term_tags", None) or {}
            co = tags.get("co_occurrence") or {}
            if isinstance(co, dict):
                partner_sets.append(
                    {
                        str(partner)
                        for partner, count in co.items()
                        if count and int(count) > 0
                    }
                )
        if not partner_sets:
            return None
        common = (
            set.intersection(*partner_sets)
            if len(partner_sets) > 1
            else partner_sets[0]
        )
        if not common:
            return None
        return "共现伙伴交集: " + ", ".join(sorted(common)[:20])

    def _update_document_co_occurrence(
        self: _ObjectInstanceDiscoveryPlatform,
        base_id: str,
        term_ids: list[str],
    ) -> None:
        """共现存储：同文档实例两两 +1（触发点=每次 discover 成功后）。

        - 去重后两两配对，双向写 ``term_tags.co_occurrence``（``{partner: 1}``）
        - 经 ``update_term_co_occurrence`` 新写路径（JSONB 原地合并 + Top-50，
          计数累加）；**不经过 update_term**（ext_attrs 怪癖）
        - 与方案 (a) 衔接：AUTO_DISCOVERED 直写实例的 co_occurrence 同样在此
          编排层完成，不依赖 action 管道

        Args:
            base_id: 本体库/系统空间标识。
            term_ids: 同文档实例 term_id 列表（含同义归并 canonical，可重复）。
        """
        unique = list(dict.fromkeys(t for t in term_ids if t))
        for i, left in enumerate(unique):
            for right in unique[i + 1 :]:
                self.update_term_co_occurrence(base_id, term_id=left, patch={right: 1})
                self.update_term_co_occurrence(base_id, term_id=right, patch={left: 1})

    def _discover_existing_object_instances(
        self: Any,
        base_id: str,
        *,
        mentions: list[dict[str, Any]],
        object_codes: list[str],
    ) -> _AnchorResult:
        """已有实例发现（词典锚定：快路命中 + 批量精确反查）。

        对抽取产出的 mention 列表做 词典快路命中 → 一次性批量精确反查拿
        term_id → 结果分发：

        - 唯一词面相等命中 1 term → ``existing``（is_new=False，evidence=mention）
        - 词面相等命中 ≥2 term → ``ambiguity``（同名多候选，进歧义裁决）
        - 精确反查落空（缓存旧/孤儿词/仅有别名或子串重叠）→ ``unanchored``
          （走新实例创建）

        v3 语义（用户拍板）：**命中词表后必须精确找到 term 才算命中**——
        全部 mentions 一次性 ``search_terms_batch(query_type="exact")``（一次
        往返替代原逐词最多 4 次串行查询）；精确找不到 → 当未命中，不做
        BM25/ilike 混合检索兜底（synonym 桶恒空，不再产出同义候选）。

        ``object_codes`` 保留以维持签名稳定（v3 锚定不做类型过滤，命中即已有实例）。

        Args:
            base_id: 本体库/系统空间标识。
            mentions: 抽取产出的 mention 列表 ``[{term_name, object_code, evidence, raw_type}]``。
            object_codes: 非结构化对象类型编码列表（本版仅透传，不参与过滤）。

        Returns:
            锚定结果分发（_AnchorResult 四桶；synonym 恒空）。
        """
        vocabulary = self._vocabulary_words(base_id)
        existing: list[dict[str, Any]] = []
        ambiguity: list[dict[str, Any]] = []
        synonym: list[dict[str, Any]] = []
        unanchored: list[dict[str, Any]] = []

        # 收集词表命中的 mention 词面（去重保序），一次性精确批量反查
        anchored_names: list[str] = []
        seen_names: set[str] = set()
        for mention in mentions:
            name = str(mention.get("term_name") or "").strip()
            if name and name in vocabulary and name not in seen_names:
                seen_names.add(name)
                anchored_names.append(name)
        batch: dict[str, Any] = {}
        if anchored_names:
            batch = self.search_terms_batch(
                base_id,
                keywords=anchored_names,
                query_type="exact",
                top_k=_ANCHOR_SEARCH_TOP_K,
            ) or {}

        for mention in mentions:
            name = str(mention.get("term_name") or "").strip()
            if not name:
                logger.debug("跳过空 mention: %s", mention)
                continue
            # 快路：词典缓存命中判定（O(1)）；未命中 → 新实例创建
            if name not in vocabulary:
                unanchored.append(mention)
                continue
            # 批量精确反查：精确找到 term 才算真命中（term_name/term_code/别名
            # 均参与 exact 匹配，命中行全部视为词面相等）
            rows = _search_result_items(batch.get(name))
            if not rows:
                # 缓存旧（词已删/改名/孤儿词）或仅别名/子串重叠 → 按未锚定处理，
                # 不报错、不建实例、不做模糊兜底
                logger.info("词典命中但精确反查落空（缓存旧或孤儿词）: %s", name)
                unanchored.append(mention)
                continue
            if len(rows) == 1:
                hit_row = _term_row_to_hit_row(rows[0])
                hit_row["evidence"] = name
                existing.append(hit_row)
            else:
                ambiguity.append(
                    {
                        "mention": name,
                        "terms": rows,
                        "object_code": mention.get("object_code"),
                        "raw_type": mention.get("raw_type"),
                        "evidence": mention.get("evidence"),
                    }
                )
        return _AnchorResult(
            existing=existing,
            ambiguity=ambiguity,
            synonym=synonym,
            unanchored=unanchored,
        )

    async def _discover_new_object_instances(
        self: Any,
        base_id: str,
        *,
        content: str,
        object_codes: list[str],
    ) -> list[dict[str, Any]]:
        """新实例发现（LLM 抽取：优先类型枚举 + 允许自动发现新类型）。

        流程：
        1. 类型枚举 = ``object_codes`` 经 ``get_term_type`` 取中文名（library 域限定，
           缺行回退 term 表对象术语行 term_name，仍无回退原始 code + 日志）
        2. 长文 16K 截断单次（不 chunk）
        3. ``build_llm`` + ``stream_invoke_with_thinking``（temp=0 由环境默认）一票抽取
        4. 严格 JSON 解析 + ``<think>`` 剥离 + 非法 JSON 重试（≤3 次退避）
        5. 类型归一：``object_code ∈ object_codes`` → 该 code；∉ → ``AUTO_DISCOVERED``
           （禁用 "UNKNOWN"），LLM 原始类型名存 ``raw_type``
        6. 词表回填：抽到就填 ``batch_create_vocabulary``（幂等去重，无门槛）

        Args:
            base_id: 本体库/系统空间标识。
            content: 输入实例 KB 全文。
            object_codes: 非结构化对象类型编码列表（优先类型枚举源）。

        Returns:
            mention 列表 ``[{term_name, object_code, evidence, raw_type}]``。

        Raises:
            RuntimeError: LLM 输出重试后仍非合法 JSON（无降级）。
        """
        type_entries = self._build_type_enumeration(base_id, object_codes)
        truncated = _truncate_content(content.strip(), _MAX_EXTRACT_CHARS)
        base_messages = _build_extract_prompt(
            type_entries=type_entries, content=truncated
        )

        last_error = ""
        mentions: list[dict[str, Any]] = []
        for attempt in range(_MAX_JSON_RETRIES):
            if attempt > 0:
                await asyncio.sleep(_JSON_RETRY_BACKOFF_SECONDS * attempt)
                retry_messages = base_messages + [
                    {
                        "role": "user",
                        "content": (
                            f"上次输出不是合法 JSON（{last_error}）。"
                            "请重新只输出严格 JSON 数组，不要任何解释。"
                        ),
                    }
                ]
            else:
                retry_messages = base_messages
            raw = await self._invoke_extract_llm(retry_messages)
            text = _llm_response_text(raw)
            parsed = _parse_mentions_json(text)
            if parsed is not None:
                mentions = _normalize_extracted_mentions(parsed, object_codes)
                break
            last_error = text[:200] if text else "空输出"
        else:
            raise RuntimeError(
                f"LLM 抽取输出非法 JSON（重试 {_MAX_JSON_RETRIES} 次仍失败）: "
                f"{last_error}"
            )

        # 词表回填：抽到就填（幂等去重），无 confidence/频次门槛
        words = [
            str(m["term_name"]).strip()
            for m in mentions
            if str(m.get("term_name") or "").strip()
        ]
        if words:
            self.batch_create_vocabulary(base_id, words=words)
            # 词表回填 → 词表已更新 → 飞轮实时（下次快路命中回填词）
            invalidate_vocabulary_cache()
        logger.info(
            "discover extraction: base_id=%s mentions=%d backfill_words=%d",
            base_id,
            len(mentions),
            len(words),
        )
        return mentions

    def _build_type_enumeration(
        self: Any,
        base_id: str,
        object_codes: list[str],
    ) -> list[dict[str, str]]:
        """类型枚举：object_codes 经 get_term_type 取中文名（library 域限定）。

        回退链：
        1. ``get_term_type``（term_type 表）命中且 type_name 可信 → 用 type_name；
           type_name 为空或与 type_code 相同（import 自动建行的英文 code 占位，
           非真实中文名）→ 视为失真，不采用；
        2. 失真/缺行 → 按 term_code 精确查 term 表对象行（``search_terms_exact``，
           term_type_code="object"，即 ``_sync_entity_terms`` 自动同步的
           term_code=对象 code / term_name=中文名 行）取 term_name——
           对象行中文名比 term_type 占位更准（如 "医疗文书" vs Concept）；
        3. 仍无 → 回退原始 code + 日志。

        Args:
            base_id: 本体库/系统空间标识（即 library 域）。
            object_codes: 调用方传入的优先类型编码列表。

        Returns:
            ``[{"code": ..., "name": ...}, ...]``。
        """
        entries: list[dict[str, str]] = []
        for code in object_codes:
            code_str = str(code)
            type_row = self.get_term_type(
                base_id, library_id=base_id, type_code=code_str
            )
            name = str(
                (type_row or {}).get("type_name")
                or (type_row or {}).get("typeName")
                or ""
            ).strip()
            if not name or name == code_str:
                # type_name 为空，或为英文 code 占位（import 自动建行）→ 失真，
                # 回退对象术语行中文名（对象行比 term_type 占位更准）
                name = self._object_term_name(base_id, code_str)
            if not name:
                name = code_str
                logger.warning(
                    "get_term_type 缺行且无对象术语行，类型枚举回退原始 code: "
                    "base_id=%s type_code=%s",
                    base_id,
                    code_str,
                )
            entries.append({"code": code_str, "name": name})
        return entries

    def _object_term_name(self: Any, base_id: str, code: str) -> str:
        """按 term_code 精确查 term 表对象行取中文名（term_type_code='object'）。

        新对象（ontologyBuild 创建）无裸 code 的 term_type 行，但
        ``_sync_entity_terms`` 会同步 term_code=对象 code 的对象术语行，
        term_name 即中文名——比回退原始 code 更准。

        Args:
            base_id: 本体库/系统空间标识（即 library 域）。
            code: 对象类型编码。

        Returns:
            对象行 term_name；无匹配或查询异常 → 空串（调用方回退原始 code）。
        """
        try:
            result = self.search_terms_exact(
                base_id,
                term_type_code="object",
                keyword=code,
                limit=1,
            )
        except Exception:
            logger.warning(
                "search_terms_exact 查询对象术语行失败，回退原始 code: "
                "base_id=%s type_code=%s",
                base_id,
                code,
                exc_info=True,
            )
            return ""
        rows = _search_result_items(result)
        if not rows:
            return ""
        name = _row_term_name(rows[0])
        if name:
            logger.info(
                "类型枚举按对象术语行回退中文名: base_id=%s type_code=%s term_name=%s",
                base_id,
                code,
                name,
            )
        return name

    async def _invoke_extract_llm(self: Any, messages: list[dict[str, str]]) -> Any:
        """调用 LLM（build_llm + stream_invoke_with_thinking，document_enrich 模式）。

        经 ``anyio.to_thread.run_sync`` 移出事件循环线程；temp=0 由
        ``build_llm`` 环境默认（DATACLOUD_LLM_TEMPERATURE 默认 0.0）。

        Args:
            messages: prompt 消息列表。

        Returns:
            累积 AIMessage（含 content）。
        """
        return await to_thread.run_sync(partial(_extract_llm_sync, messages=messages))

    async def _register_object_file(
        self: _ObjectInstanceDiscoveryPlatform,
        *,
        base_id: str,
        object_code: str,
        term_name: str,
        term_id: str,
        action_result: dict[str, Any],
    ) -> None:
        """文件登记：复用 document.py 的 ``_build_object_file_status`` 模式。

        登记条目含 sessionId / objectName / objectCode / fileName / filePath /
        version / statusCd（待整理）/ extContent{kb_resource_id, kb_id,
        kb_directory, term_id=强校验值}。

        Args:
            base_id: 本体库/系统空间标识。
            object_code: 新实例对象类型编码。
            term_name: 新实例名称。
            term_id: 强校验后的 term_id（write action 响应）。
            action_result: write action 归一化响应（提供 fileName/termId）。
        """
        term_name = term_name.strip()
        file_path = f"/{object_code}/{term_name}.md"
        document = DocumentObjectItem(
            termId=term_id,
            termName=term_name,
            termCode=term_name,
            termTypeCode=object_code,
            filePath=file_path,
            kbResourceId="",
        )
        object_scope = DocumentEnrichObjectScope(
            objectCode=object_code,
            objectName=term_name,
        )
        object_file = _build_object_file_status(
            session_id=_current_session_id(),
            document=document,
            object_scope=object_scope,
            status=DocumentProcessingStatus.PENDING_ORGANIZATION,
            labels=_PENDING_LABELS,
            action_result=action_result,
        )
        await self.save_or_update_object_files(base_id, object_files=[object_file])

    def _establish_mention_relation(
        self: _ObjectInstanceDiscoveryPlatform,
        *,
        base_id: str,
        source_term_id: str,
        target_term_id: str,
    ) -> bool:
        """建立「提及」关系（源→目标，单向、幂等）。

        先按源实例 + 关键词「提及」查重；已存在同源同目标的提及关系则跳过，
        否则创建 camelCase 三字段关系。方向固定为 源=输入实例 → 目标=发现实例，
        不建反向。

        Args:
            base_id: 本体库/系统空间标识。
            source_term_id: 输入实例 term_id（关系源）。
            target_term_id: 发现实例 term_id（关系目标）。

        Returns:
            True=本次创建了关系；False=关系已存在（跳过）。

        Raises:
            list/create 失败时原样上抛（无降级）。
        """
        page = self.list_term_relations(
            base_id, source_term_id=source_term_id, keyword="提及"
        )
        for row in _relation_items(page):
            relation_name = str(
                row.get("relation_name") or row.get("relationName") or ""
            )
            target = str(row.get("target_term_id") or row.get("targetTermId") or "")
            if relation_name == "提及" and target == target_term_id:
                return False
        self.create_term_relation(
            base_id,
            relation={
                "sourceTermId": source_term_id,
                "targetTermId": target_term_id,
                "relationName": "提及",
                # relationCategory 必填非空：opengauss 兼容模式下空字符串
                # 被转为 NULL，违反 term_relation.relation_category NOT NULL；
                # 提及属业务关系，按库中既有约定（ONTOLOGY/BUSINESS）取 BUSINESS。
                "relationCategory": "BUSINESS",
            },
        )
        return True


def _extract_written_term_id(action_result: dict[str, Any]) -> str:
    """term_id 强校验：从 write action 响应中提取 records[0] 的 term_id。

    响应先经 ``unwrap_action_result`` 归一化为 ``{records, total, meta}``；
    取 ``records[0].term_id / termId``，缺失或为空则抛错（不延迟、不做 pending）。

    Args:
        action_result: write action 原始响应（可为未归一化信封）。

    Returns:
        强校验非空的 term_id（去除首尾空白）。

    Raises:
        ObjectInstanceWriteMissingTermIdError: records 缺失或 term_id 缺失/为空。
    """
    normalized = unwrap_action_result(action_result)
    records = normalized.get("records")
    first = (
        records[0]
        if isinstance(records, list) and records and isinstance(records[0], dict)
        else None
    )
    term_id = (
        str(first.get("term_id") or first.get("termId") or "").strip() if first else ""
    )
    if not term_id:
        raise ObjectInstanceWriteMissingTermIdError(
            "write action response is missing term_id"
        )
    return term_id


def _extract_imported_term_id(result: dict[str, Any]) -> str:
    """term_id 强校验：从 create_term/import_terms 响应中提取 term_ids[0]。

    自动发现直写通道（AUTO_DISCOVERED）的强校验等价物：
    ``create_term`` 返回 ``{created, updated, skipped, term_ids, errors}``，
    取 ``term_ids[0]``，缺失或为空则抛错（与 action 管道同样不延迟、不做 pending）。

    Args:
        result: create_term/import_terms 归一化响应。

    Returns:
        强校验非空的 term_id。

    Raises:
        ObjectInstanceWriteMissingTermIdError: term_ids 缺失或首项为空。
    """
    term_ids = result.get("term_ids") or result.get("termIds") or []
    term_id = (
        str(term_ids[0]).strip()
        if isinstance(term_ids, list) and term_ids and term_ids[0]
        else ""
    )
    if not term_id:
        raise ObjectInstanceWriteMissingTermIdError(
            "create_term response is missing term_id"
        )
    return term_id


def _relation_items(page: dict[str, Any]) -> list[dict[str, Any]]:
    """从 list_term_relations 响应中提取关系记录行（兼容 data/items/records）。"""
    rows = page.get("data") or page.get("items") or page.get("records") or []
    return [row for row in rows if isinstance(row, dict)]


def _search_result_items(result: Any) -> list[dict[str, Any]]:
    """从 search_terms 响应提取术语行（兼容 QueryResult dataclass / dict 信封）。

    TermItem 为 frozen dataclass → asdict 归一化为 dict，供锚定判定使用。
    """
    if result is None:
        return []
    if isinstance(result, dict):
        raw = result.get("items") or result.get("data") or result.get("records") or []
    else:
        raw = getattr(result, "items", None)
        if raw is None:
            raw = getattr(result, "data", None) or []
    rows: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            rows.append(item)
        elif hasattr(item, "__dataclass_fields__"):
            rows.append(asdict(item))
        else:
            rows.append(
                {
                    key: getattr(item, key)
                    for key in vars(item)
                    if not key.startswith("_")
                }
            )
    return rows


def _row_term_name(row: dict[str, Any]) -> str:
    """取术语行的标准名称（兼容 camelCase / snake_case）。"""
    return str(row.get("term_name") or row.get("termName") or "").strip()


def _term_row_to_hit_row(row: dict[str, Any]) -> dict[str, Any]:
    """把 search_terms 术语行归一化为已有实例候选行（_build_existing_hit 输入形态）。

    兼容 TermItem 的 ``term_type`` 字段与既有 ``term_type_code`` / ``termTypeCode``。
    """
    return {
        "term_id": str(row.get("term_id") or row.get("termId") or ""),
        "term_code": str(row.get("term_code") or row.get("termCode") or ""),
        "term_name": str(row.get("term_name") or row.get("termName") or ""),
        "term_type_code": str(
            row.get("term_type_code")
            or row.get("termTypeCode")
            or row.get("term_type")
            or ""
        ),
        "file_name": str(row.get("file_name") or row.get("fileName") or "") or None,
        "kb_resource_id": str(
            row.get("kb_resource_id") or row.get("kbResourceId") or ""
        )
        or None,
        "kb_id": str(row.get("kb_id") or row.get("kbId") or "") or None,
    }


def _build_existing_hit(row: dict[str, Any]) -> ObjectInstanceDiscoveryHit:
    """把已有实例候选行组装为发现结果项（is_new=False）。

    候选行字段与 ObjectInstanceHit 对齐：
    term_id / term_code / term_name / term_type_code（或 term_type）/
    file_name / kb_resource_id / kb_id / evidence
    （同时兼容 camelCase 变体）。
    """
    evidence = row.get("evidence")
    return ObjectInstanceDiscoveryHit(
        instance_id=str(row["term_id"]),
        instance_code=str(row.get("term_code") or row.get("termCode") or ""),
        instance_name=str(row.get("term_name") or row.get("termName") or ""),
        object_code=str(
            row.get("term_type_code")
            or row.get("termTypeCode")
            or row.get("term_type")
            or ""
        ),
        file_name=str(row.get("file_name") or row.get("fileName") or "") or None,
        kb_resource_id=str(row.get("kb_resource_id") or row.get("kbResourceId") or "")
        or None,
        kb_id=str(row.get("kb_id") or row.get("kbId") or "") or None,
        is_new=False,
        evidence=str(evidence) if evidence is not None else None,
    )


# ── LLM 抽取辅助──────────────────────────────────────────


def _build_extract_prompt(
    type_entries: list[dict[str, str]], content: str
) -> list[dict[str, str]]:
    """构造抽取 prompt。

    system 承载：优先类型枚举（object_code=类型中文名）、AUTO_DISCOVERED
    归一规则、严格 JSON 输出 schema；user 直接承载截断后的文档正文
    （不加前缀，保证长度 ≤ 16K 上限）。

    Args:
        type_entries: 类型枚举 ``[{"code", "name"}]``（TermType 中文名，缺行回退 code）。
        content: 已截断的文档正文。

    Returns:
        OpenAI 风格消息列表（system + user）。
    """
    enum_lines = "\n".join(f"{entry['code']}={entry['name']}" for entry in type_entries)
    system = (
        "你是企业知识库对象实例抽取器。请从 user 消息提供的文档正文中，"
        "抽取出现的对象实例（业务实体），输出严格 JSON 数组。\n\n"
        "优先类型枚举（object_code=类型中文名）：\n"
        f"{enum_lines}\n\n"
        "实体类型属于上述枚举时 object_code 填对应编码；不属于上述任何枚举时，"
        f"object_code 固定填 {_AUTO_DISCOVERED_CODE}，并在 raw_type 字段中给出"
        "你识别到的原始类型名。\n\n"
        "输出格式（严格 JSON 数组，每条含 term_name / object_code / evidence / raw_type）：\n"
        '[{"term_name": "实例名称", "object_code": "类型编码或 AUTO_DISCOVERED",'
        ' "evidence": "文档中的原文片段", "raw_type": "原始类型名"}]\n'
        "只输出 JSON 数组，不要任何解释或 markdown 代码块。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]


def _truncate_content(content: str, max_chars: int) -> str:
    """长文截断单次（不 chunk）。

    超限时取前 ``max_chars`` 字符并以省略号收尾，标识截断位置。

    Args:
        content: 原始文本。
        max_chars: 截断上限（字符数）。

    Returns:
        截断后文本（未超限时原样返回）。
    """
    if len(content) <= max_chars:
        return content
    return content[: max_chars - 1].rstrip() + "…"


def _extract_llm_sync(messages: list[dict[str, str]]) -> Any:
    """同步调用 LLM 抽取（移出事件循环线程执行）。

    显式传参：thinking=False（抽取输出严格 JSON 结构化数组，无需思考链，
    禁用可显著缩短响应时间）；temperature=0.0（固定零温度保证结果确定性，
    对齐 spec D-1，避免环境温度漂移影响抽取质量）。
    ``stream_invoke_with_thinking`` 在无回调时等价 ``invoke``（返回累积 AIMessage）。

    Args:
        messages: prompt 消息列表。

    Returns:
        累积 AIMessage（含 content）。
    """
    llm = build_llm(thinking=False, temperature=0.0)
    return stream_invoke_with_thinking(llm, messages, on_event=None)


def _llm_response_text(raw: Any) -> str:
    """从 LLM 响应中提取纯文本内容（兼容 str / AIMessage / 多块 list）。"""
    content = getattr(raw, "content", None)
    if content is None:
        content = raw
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if text:
                    parts.append(str(text))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content or "")


def _parse_mentions_json(text: str) -> list[dict[str, Any]] | None:
    """解析 LLM 输出的严格 JSON 数组（含前导 <think> 剥离）。

    Args:
        text: LLM 输出原文。

    Returns:
        mention 列表（dict 行）；非合法 JSON 数组时返回 None（触发重试）。
    """
    stripped = _LEADING_THINKING_PATTERN.sub("", text).strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, list) else None


def _normalize_extracted_mentions(
    parsed: list[Any], object_codes: list[str]
) -> list[dict[str, Any]]:
    """类型归一 + 字段净化。

    - ``object_code ∈ object_codes`` → 保留该 code
    - ``object_code ∉ object_codes`` → ``AUTO_DISCOVERED``（禁用 "UNKNOWN"），
      原始类型名保留在 ``raw_type``
    - 空白 term_name 行丢弃；evidence / raw_type 非空才写入输出

    Args:
        parsed: JSON 解析后的列表（可能含非 dict 脏行）。
        object_codes: 调用方优先类型编码列表。

    Returns:
        归一化 mention 列表 ``[{term_name, object_code, evidence?, raw_type?}]``。
    """
    allowed = set(object_codes)
    normalized: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        term_name = str(item.get("term_name") or item.get("termName") or "").strip()
        if not term_name:
            continue
        code = str(item.get("object_code") or item.get("objectCode") or "").strip()
        if code not in allowed:
            code = _AUTO_DISCOVERED_CODE
        row: dict[str, Any] = {"term_name": term_name, "object_code": code}
        evidence = item.get("evidence")
        if evidence is not None and str(evidence).strip():
            row["evidence"] = str(evidence).strip()
        raw_type = item.get("raw_type") or item.get("rawType")
        if raw_type is not None and str(raw_type).strip():
            row["raw_type"] = str(raw_type).strip()
        normalized.append(row)
    return normalized


# ── 同步裁决辅助───────────────────────────────────────────────


def _judge_llm_sync(messages: list[dict[str, str]]) -> Any:
    """同步调用裁决 LLM（移出事件循环线程执行）。

    显式传参：thinking=False（裁决为单次判定，输出严格 JSON 对象，
    禁用思考链保持快速响应）；temperature=0.0（一票判定需确定性，
    固定零温度避免环境温度漂移引入不一致）。

    Args:
        messages: prompt 消息列表。

    Returns:
        累积 AIMessage（含 content）。
    """
    llm = build_llm(thinking=False, temperature=0.0)
    return stream_invoke_with_thinking(llm, messages, on_event=None)


def _parse_judge_json(text: str) -> dict[str, Any] | None:
    """解析裁决 LLM 输出的严格 JSON 对象（含前导 <think> 剥离）。

    Args:
        text: LLM 输出原文。

    Returns:
        裁决对象（dict）；非合法 JSON 对象时返回 None（触发重试）。
    """
    stripped = _LEADING_THINKING_PATTERN.sub("", text).strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _build_synonym_prompt(
    *,
    mention: str,
    mention_context: str,
    term_row: dict[str, Any],
    partner_overlap: str | None,
) -> list[dict[str, str]]:
    """同义裁决 prompt（judge_synonym 形态）。

    Args:
        mention: 候选 mention（实体A）。
        mention_context: mention 在文档中的原文片段（evidence，可为空）。
        term_row: 已有 term 行（实体B）。
        partner_overlap: 共现伙伴交集段（可为 None）。

    Returns:
        system + user 消息列表。
    """
    system = (
        "你是企业知识库实体归并裁决器。判断两个实体是否指向同一现实实体"
        "（全称/简称/别名关系也算同一实体）。只输出严格 JSON 对象，不要任何解释。"
    )
    parts = [f"实体A: {mention}"]
    if mention_context:
        parts.append(f"实体A上下文: {mention_context}")
    parts.append(
        f"实体B: {_row_term_name(term_row)}"
        f"（类型: {term_row.get('term_type_code') or '未知'}）"
    )
    if partner_overlap:
        parts.append(partner_overlap)
    parts.append(
        '判断 A/B 是否同一实体 → 输出 {"same": bool, "canonical": "主实体ID或名称"}'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(parts)},
    ]


def _build_ambiguity_prompt(
    *,
    mention: str,
    term_contexts: list[str],
    partner_overlap: str | None,
) -> list[dict[str, str]]:
    """歧义裁决 prompt（judge_ambiguity 形态）。

    Args:
        mention: 同词面 mention。
        term_contexts: 各 term 的语境描述列表。
        partner_overlap: 共现伙伴交集段（可为 None）。

    Returns:
        system + user 消息列表。
    """
    system = (
        "你是企业知识库同名实体裁决器。判断同词面出现在多个语境时，"
        "是同一实体还是同名异义。只输出严格 JSON 对象，不要任何解释。"
    )
    context_lines = "\n".join(
        f"语境{i + 1}: {context}" for i, context in enumerate(term_contexts)
    )
    parts = [
        f"词面 '{mention}' 出现在多个语境，可能是同一实体或多个同名异义实体。",
        context_lines,
    ]
    if partner_overlap:
        parts.append(partner_overlap)
    parts.append(
        '判断：同一实体 or 同名异义 → {"same_entity": bool, "entity_names": ["主实体名称", ...]}'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(parts)},
    ]


def _mention_object_code(candidate: dict[str, Any]) -> str:
    """裁决后新实例类型规则：能定类型用该类型，定不了 → AUTO_DISCOVERED。

    Args:
        candidate: 冲突候选（含抽取产出的 object_code）。

    Returns:
        新实例 object_code（缺失/空 → AUTO_DISCOVERED）。
    """
    code = str(candidate.get("object_code") or "").strip()
    return code if code else _AUTO_DISCOVERED_CODE


def _pick_canonical_term_id(
    terms: list[dict[str, Any]], entity_names: list[Any]
) -> str:
    """歧义归并选主 term：优先与裁决 entity_names 匹配的 term，否则取第一个。

    Args:
        terms: 同名多候选 term 行列表。
        entity_names: 裁决输出的主实体名列表。

    Returns:
        主 term_id（空串 = 无法确定 → 调用方跳过归并）。
    """
    names = {str(n).strip() for n in entity_names if str(n).strip()}
    for row in terms:
        if _row_term_name(row) in names:
            return str(row.get("term_id") or row.get("termId") or "")
    return str(terms[0].get("term_id") or terms[0].get("termId") or "")
