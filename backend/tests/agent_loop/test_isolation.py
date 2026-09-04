"""The P03 kernel imports without database, web, worker or network clients."""
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

SCRIPT = r"""
import sys
sys.path.insert(0, sys.argv[1])
forbidden = ("app.core", "app.models", "app.routers", "app.workers", "app.services",
             "sqlalchemy", "pydantic_settings", "httpx", "anthropic", "fastapi")
attempts = []
class Blocker:
    def find_spec(self, name, path=None, target=None):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden):
            attempts.append(name)
            raise ModuleNotFoundError("blocked", name=name)
        return None
sys.meta_path.insert(0, Blocker())
import app.agents.conversation.budget
import app.agents.conversation.policy
import app.agents.conversation.tool_executor
import app.agents.conversation.loop
loaded = [name for name in sys.modules if any(name == p or name.startswith(p + ".") for p in forbidden)]
if attempts or loaded:
    print("VIOLATION", attempts, loaded)
    raise SystemExit(2)
print("P03_ISOLATION_OK")
"""


def test_p03_kernel_import_has_no_database_web_worker_or_client_side_effects():
    result = subprocess.run([sys.executable, "-c", SCRIPT, str(BACKEND)], capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "P03_ISOLATION_OK" in result.stdout
