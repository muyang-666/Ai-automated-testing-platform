import re
from typing import Any

_VARIABLE_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def get_by_json_path(data: Any, path: str) -> Any:
    """从 dict/list 结构中按简单 JSONPath 取值。

    支持格式: $.data.token, $.data.items[0].id, $.code, $
    """
    if data is None or not path:
        return None

    path = path.strip()

    if path == "$":
        return data

    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]

    if not path:
        return data

    segments = path.split(".")
    current = data

    for seg in segments:
        if current is None:
            return None

        # 处理数组索引: key[n]
        index_match = re.match(r"^(.+?)\[(\d+)\]$", seg)
        if index_match:
            key = index_match.group(1)
            idx = int(index_match.group(2))
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
            if not isinstance(current, list) or idx >= len(current):
                return None
            current = current[idx]
        else:
            if not isinstance(current, dict) or seg not in current:
                return None
            current = current[seg]

    return current


def extract_variables(response_json: Any, extract_rules: Any) -> dict:
    """根据变量提取规则，从响应 JSON 中提取变量。

    extract_rules 示例: {"token": "$.data.token", "user_id": "$.data.user_id"}
    返回: {"variables": {...}, "errors": [...]}
    """
    if extract_rules is None:
        return {"variables": {}, "errors": []}

    if not isinstance(extract_rules, dict):
        return {"variables": {}, "errors": ["extract_rules 必须是 dict"]}

    variables = {}
    errors = []

    for var_name, json_path in extract_rules.items():
        if not isinstance(json_path, str):
            errors.append(f"变量 {var_name} 的路径不是合法字符串")
            continue

        value = get_by_json_path(response_json, json_path)
        if value is None:
            # 路径不存在（也可能是值就是 null）
            # 用 path 本身做二次校验：非空路径且非 "$"
            if json_path and json_path != "$":
                check = get_by_json_path(response_json, json_path)
                if check is None and json_path not in ("$",):
                    errors.append(f"变量 {var_name} 提取失败，路径 {json_path} 不存在")
                    continue
        variables[var_name] = value

    return {"variables": variables, "errors": errors}


def _replace_string(value: str, context: dict) -> tuple[Any, list[str]]:
    """替换字符串中的 ${变量名}，返回 (替换结果, errors列表)。

    如果整个字符串恰好是 "${var}" 且 context[var] 不是字符串，保留原始类型。
    """
    # 整体匹配: 整个字符串就是一个变量引用
    full_match = _VARIABLE_PATTERN.fullmatch(value)
    if full_match:
        var_name = full_match.group(1)
        if var_name in context:
            return context[var_name], []
        else:
            return value, [f"变量 {var_name} 不存在"]

    # 部分匹配: 字符串中包含 ${var}
    errors = []
    result = value
    for match in _VARIABLE_PATTERN.finditer(value):
        var_name = match.group(1)
        if var_name not in context:
            errors.append(f"变量 {var_name} 不存在")

    def replacer(m):
        var_name = m.group(1)
        if var_name in context:
            val = context[var_name]
            return str(val) if not isinstance(val, str) else val
        return m.group(0)

    result = _VARIABLE_PATTERN.sub(replacer, value)
    return result, errors


def replace_variables(data: Any, context: dict) -> dict:
    """递归替换数据结构中的 ${变量名} 占位符。

    支持 str / dict / list，int/float/bool/None 原样返回。
    返回: {"data": 替换后的数据, "errors": [...]}
    """
    if context is None:
        context = {}

    result, errors = _replace_recursive(data, context)
    return {"data": result, "errors": errors}


def _replace_recursive(data: Any, context: dict) -> tuple[Any, list[str]]:
    """递归替换，汇总所有层级的 errors。"""
    errors = []

    if isinstance(data, str):
        replaced, errs = _replace_string(data, context)
        errors.extend(errs)
        return replaced, errors

    if isinstance(data, dict):
        new_dict = {}
        for key, value in data.items():
            new_value, errs = _replace_recursive(value, context)
            new_dict[key] = new_value
            errors.extend(errs)
        return new_dict, errors

    if isinstance(data, list):
        new_list = []
        for item in data:
            new_item, errs = _replace_recursive(item, context)
            new_list.append(new_item)
            errors.extend(errs)
        return new_list, errors

    return data, errors
