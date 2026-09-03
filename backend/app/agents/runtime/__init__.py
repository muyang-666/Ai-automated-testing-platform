# 注意：本包 __init__ 保持为空。
# registry 包导入 runtime.errors 时会先执行本包 __init__；
# 若在此急切导入 runner（而 runner 又导入 registry），会形成循环导入。
# 请显式从子模块导入，如 from app.agents.runtime.runner import AgentRunner。
