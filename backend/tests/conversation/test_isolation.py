"""P01 合同：全新子进程隔离导入与网络/配置保护（含逐项负向自检与故障注入）。

- 保护在导入任何 conversation 模块之前安装；
- 记录每一次被禁止的导入尝试与被禁止的连接尝试：正式阶段即使异常被捕获，
  收尾仍判失败；
- connect 与 create_connection 分别有独立的检查结果，互不复用；
- 校准自检与正式导入阶段分段：只清理校准期间记录，不清正式阶段的尝试；
- 故障注入：把某一连接保护入口替换为空操作时，对应自检必须失败（不恢复真实
  网络调用）；
- 加载了声明范围内的数据库/配置/客户端模块或业务子树即失败。
保护只用于本测试进程，不是完整宿主沙箱证明。
"""

import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]  # backend/

CHILD_SCRIPT = r"""
import sys

backend, mode = sys.argv[1], sys.argv[2]
sys.path.insert(0, backend)

FORBIDDEN_PREFIXES = (
    "app.core", "app.models", "app.routers", "app.workers", "app.services",
    "app.main", "sqlalchemy", "pydantic_settings", "httpx", "fastapi",
)
blocked_import_attempts = []
denied_connects = []

class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name == "app":
            return None
        if name.startswith("app.") and not (name == "app.agents" or name.startswith("app.agents.")):
            blocked_import_attempts.append(name)
            raise ModuleNotFoundError(f"[P01隔离] 禁止导入 {name}", name=name)
        for prefix in FORBIDDEN_PREFIXES:
            if name == prefix or name.startswith(prefix + "."):
                blocked_import_attempts.append(name)
                raise ModuleNotFoundError(f"[P01隔离] 禁止导入 {name}", name=name)
        return None

sys.meta_path.insert(0, _Blocker())

import socket  # noqa: E402

class _NetworkGuardError(RuntimeError):
    pass

def _deny(entry):
    def deny(*args, **kwargs):
        denied_connects.append(entry)
        raise _NetworkGuardError(f"[P01隔离] 网络连接被禁止 ({entry})")
    return deny

socket.socket.connect = _deny("connect")  # type: ignore[method-assign]
if mode == "disable_create_connection":
    # 故障注入：把该入口替换成“无连接空操作”，对应自检必须失败
    socket.create_connection = lambda *a, **k: None  # type: ignore[assignment]
else:
    socket.create_connection = _deny("create_connection")  # type: ignore[method-assign]

# ── 校准 1：被禁模块必须真的被拦截（仅用于证明保护有效，记录随后清空）──
negative_import_ok = False
try:
    import app.models  # noqa: F401
except ModuleNotFoundError:
    negative_import_ok = True
if not negative_import_ok:
    print("NEGATIVE_IMPORT_CHECK_FAILED")
    sys.exit(4)
blocked_import_attempts.clear()

# ── 校准 2：connect 与 create_connection 各自独立自检（随后清空校准记录）──
check_connect = False
probe = socket.socket()
try:
    probe.connect(("127.0.0.1", 1))
except _NetworkGuardError:
    check_connect = True
finally:
    probe.close()

check_create = False
try:
    socket.create_connection(("127.0.0.1", 1))
except _NetworkGuardError:
    check_create = True
if not check_connect or not check_create:
    print("NEGATIVE_NETWORK_CHECK_FAILED", "connect=", check_connect, "create=", check_create)
    sys.exit(5)
denied_connects.clear()  # 只清校准记录，正式阶段尝试另行记录

# ── 正式阶段：模拟“尝试连接但捕获保护异常”─ 必须在收尾判失败 ──
if mode == "formal_connect_attempt":
    try:
        socket.create_connection(("127.0.0.1", 1))
    except _NetworkGuardError:
        pass  # 即使被捕获，收尾也要因为已记录该尝试而失败

# ── 正式导入全部 conversation 纯合同模块 ──
import app.agents.conversation.messages        # noqa: E402
import app.agents.conversation.events           # noqa: E402
import app.agents.conversation.contracts        # noqa: E402
import app.agents.conversation.tool_validation  # noqa: E402

# ── 收尾：加载违禁模块、正式导入被禁尝试、正式连接尝试均判失败 ──
violations = []
for module_name in sys.modules:
    for prefix in FORBIDDEN_PREFIXES:
        if module_name == prefix or module_name.startswith(prefix + "."):
            violations.append(module_name)
if violations or blocked_import_attempts or denied_connects:
    print("VIOLATIONS:", sorted(set(violations)),
          "BLOCKED_IMPORTS:", sorted(set(blocked_import_attempts)),
          "DENIED_CONNECTS:", sorted(set(denied_connects)))
    sys.exit(3)
print("ISOLATION_OK")
"""


def _run_child(mode: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", CHILD_SCRIPT, str(BACKEND_DIR), mode],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_conversation_modules_import_without_database_config_or_clients():
    result = _run_child("normal")
    assert result.returncode == 0, f"子进程失败 rc={result.returncode}\n{result.stdout}\n{result.stderr}"
    assert "ISOLATION_OK" in result.stdout


def test_formal_connect_attempt_caught_still_fails():
    result = _run_child("formal_connect_attempt")
    assert result.returncode != 0, "正式阶段连接尝试被捕获后仍应判失败"
    assert "DENIED_CONNECTS" in result.stdout


def test_disabled_create_connection_guard_makes_selfcheck_fail():
    result = _run_child("disable_create_connection")
    assert result.returncode != 0, "把 create_connection 保护替换为空操作后自检必须失败"
    assert "NEGATIVE_NETWORK_CHECK_FAILED" in result.stdout
