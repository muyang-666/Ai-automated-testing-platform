"""用例确定性校验器：纯函数、不查数据库、无副作用。

- Schema 校验：结构/类型；
- 业务规则校验：取值/枚举/必填语义；
- 去重与覆盖矩阵：确定性算法，不依赖模型自报；
- 去重指纹（V2.1-T05.1 修复）：
  function = case_name/name + steps_json/steps + expected_result + case_type
  api      = method + canonical URL + body + expected_result + case_type
  指纹输出为 SHA-256 摘要，中间明文只存在于内存、绝不返回；
  已有用例可自带 dedup_fingerprint（由同一算法生成）直接参与比较；
- 全部函数可独立单测，供工具层与后续 Workflow 复用。
"""

import hashlib
import json
from urllib.parse import parse_qsl, urlencode, urlsplit

FUNCTION_ALLOWED_CASE_TYPES = {"正常场景", "异常场景", "边界场景", "业务规则场景", "其他"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2"}
ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}


def normalize_case_name(text) -> str:
    return (text or "").strip().lower()


# ── Canonical 表达（用于指纹；不修改输入、不返回明文） ──


def canonical_json(value) -> str:
    """把 dict/list/JSON 字符串/标量转为稳定表达。

    - dict/list：sort_keys 递归稳定序列化（key 顺序无关）；
    - JSON 字符串：先尝试解析再 canonical；解析失败使用原字符串（稳定 fallback）；
    - None → "<null>"。
    """
    if value is None:
        return "<null>"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if isinstance(value, str):
        text = value.strip()
        try:
            data = json.loads(text)
        except Exception:
            return text
        if isinstance(data, (dict, list)):
            return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return text
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def canonical_url(raw_url) -> str:
    """URL 稳定表达：scheme/netloc 小写、path 去尾斜杠、query 参数排序。

    - 含 <<变量>> 占位时不解析（稳定原样返回）；
    - 解析失败时使用稳定 fallback（整体小写）。
    """
    url = (raw_url or "").strip()
    if not url:
        return ""
    if "<<" in url:
        return url
    try:
        parts = urlsplit(url)
        scheme = (parts.scheme or "").lower()
        netloc = (parts.netloc or "").lower()
        path = parts.path.rstrip("/")
        query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
        base = f"{scheme}://{netloc}{path}"
        return f"{base}?{query}" if query else base
    except Exception:
        return url.lower()


def _case_name(case: dict) -> str:
    return normalize_case_name(case.get("case_name") or case.get("name"))


def _case_steps(case: dict) -> str:
    return canonical_json(case.get("steps_json", case.get("steps")))


def _case_type(case: dict) -> str:
    return str(case.get("case_type") or "").strip()


def case_fingerprint(case_kind: str, case: dict) -> str:
    """确定性用例指纹（SHA-256 摘要，不含明文）。

    已有用例（如 list_existing_cases 摘要）可自带 dedup_fingerprint，
    由同一算法预生成，直接复用。
    """
    if isinstance(case, dict) and case.get("dedup_fingerprint"):
        return case["dedup_fingerprint"]

    if case_kind == "function":
        canonical = "|".join(
            [
                "function",
                _case_name(case),
                _case_steps(case),
                canonical_json(case.get("expected_result")),
                _case_type(case),
            ]
        )
    else:
        canonical = "|".join(
            [
                "api",
                str(case.get("method") or "").strip().upper(),
                canonical_url(case.get("url")),
                canonical_json(case.get("body")),
                canonical_json(case.get("expected_result")),
                _case_type(case),
            ]
        )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Schema 校验（结构/类型） ──


def validate_function_case_schema(item) -> list[str]:
    errors = []
    if not isinstance(item, dict):
        return ["不是对象"]
    if not isinstance(item.get("case_name") or "", str):
        errors.append("case_name 必须是字符串")
    if not isinstance(item.get("steps_json", []), list):
        errors.append("steps_json 必须是数组")
    if not isinstance(item.get("expected_result") or "", str):
        errors.append("expected_result 必须是字符串")
    test_data = item.get("test_data_json")
    if test_data is not None and not isinstance(test_data, dict):
        errors.append("test_data_json 必须是对象")
    return errors


def validate_api_case_schema(item) -> list[str]:
    errors = []
    if not isinstance(item, dict):
        return ["不是对象"]
    if not isinstance(item.get("name") or "", str):
        errors.append("name 必须是字符串")
    method = item.get("method")
    if method is not None and not isinstance(method, str):
        errors.append("method 必须是字符串")
    if not isinstance(item.get("url") or "", str):
        errors.append("url 必须是字符串")
    headers = item.get("headers")
    if headers is not None and not isinstance(headers, dict):
        errors.append("headers 必须是对象")
    body = item.get("body")
    if body is not None and not isinstance(body, (dict, list, str)):
        errors.append("body 必须是对象/数组/字符串")
    expected = item.get("expected_result")
    if expected is not None and not isinstance(expected, (dict, str)):
        errors.append("expected_result 必须是对象或字符串")
    return errors


# ── 业务规则校验（取值/枚举/必填语义） ──


def validate_function_case_business(item) -> list[str]:
    errors = []
    if not (item.get("case_name") or "").strip():
        errors.append("缺少 case_name")
    if not item.get("steps_json"):
        errors.append("steps_json 为空")
    if not (item.get("expected_result") or "").strip():
        errors.append("缺少 expected_result")
    if item.get("case_type") and item["case_type"] not in FUNCTION_ALLOWED_CASE_TYPES:
        errors.append(f"case_type 非法: {item.get('case_type')}")
    if item.get("priority") and item["priority"] not in ALLOWED_PRIORITIES:
        errors.append(f"priority 非法: {item.get('priority')}")
    return errors


def validate_api_case_business(item) -> list[str]:
    errors = []
    if not (item.get("name") or "").strip():
        errors.append("缺少 name")
    method = str(item.get("method") or "").strip().upper()
    if method and method not in ALLOWED_METHODS:
        errors.append(f"method 非法: {method}")
    if not (item.get("url") or "").strip():
        errors.append("缺少 url")
    if item.get("case_type") and item["case_type"] not in FUNCTION_ALLOWED_CASE_TYPES:
        errors.append(f"case_type 非法: {item.get('case_type')}")
    if item.get("priority") and item["priority"] not in ALLOWED_PRIORITIES:
        errors.append(f"priority 非法: {item.get('priority')}")
    return errors


# ── 去重（确定性指纹分组，保留每组首个出现） ──


def find_duplicates(case_kind: str, candidates: list[dict], existing: list[dict] | None = None):
    """返回 (keep_indexes, duplicates)。

    keep_indexes：每组重复中的首个候选下标；duplicates：[{fingerprint,
    first_position, first_origin, duplicate_position, duplicate_origin}]。
    """
    seen: dict[str, tuple[int, str]] = {}
    keep_indexes: list[int] = []
    duplicates: list[dict] = []

    # 已有用例先注册指纹：与已有重复的候选被丢弃（保留已有，不保留候选）
    items = [("existing", j, e) for j, e in enumerate(existing or [])]
    items += [("candidate", i, c) for i, c in enumerate(candidates)]

    for origin, position, item in items:
        fingerprint = case_fingerprint(case_kind, item)
        if fingerprint in seen:
            first_position, first_origin = seen[fingerprint]
            duplicates.append(
                {
                    "fingerprint": fingerprint,
                    "first_position": first_position,
                    "first_origin": first_origin,
                    "duplicate_position": position,
                    "duplicate_origin": origin,
                }
            )
        else:
            seen[fingerprint] = (position, origin)
            if origin == "candidate":
                keep_indexes.append(position)

    return keep_indexes, duplicates


# ── 覆盖矩阵（确定性聚合，不接受模型自报覆盖率） ──


def compute_coverage(clauses: list[dict], candidates: list[dict]) -> dict:
    clause_ids = {c.get("clause_id") for c in clauses if c.get("clause_id")}
    covered: dict[str, list] = {}
    unknown_refs: list[dict] = []

    for candidate in candidates:
        candidate_id = candidate.get("candidate_id") or candidate.get("name")
        for clause_id in candidate.get("covered_clause_ids") or []:
            if clause_id in clause_ids:
                covered.setdefault(clause_id, []).append(candidate_id)
            else:
                unknown_refs.append({"candidate_id": candidate_id, "clause_id": clause_id})

    matrix = []
    for clause in clauses:
        clause_id = clause.get("clause_id")
        matrix.append(
            {
                "clause_id": clause_id,
                "text": clause.get("text"),
                "covered_by": covered.get(clause_id, []),
                "covered": clause_id in covered,
            }
        )

    uncovered_clause_ids = [row["clause_id"] for row in matrix if not row["covered"]]
    return {
        "matrix": matrix,
        "covered_count": sum(1 for row in matrix if row["covered"]),
        "uncovered_count": len(uncovered_clause_ids),
        "uncovered_clause_ids": uncovered_clause_ids,
        "unknown_refs": unknown_refs,
    }
