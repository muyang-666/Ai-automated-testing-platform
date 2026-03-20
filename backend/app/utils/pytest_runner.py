# 把某个pytes测试文件启动运行，然后把结果整理成结构化数据返回

import re                 # 导入 Python 的正则表达式模块。
import subprocess         # 导入 Python 的子进程模块。 这个子进程专门去执行 pytest
import sys                # 导入 Python 的系统模块。
from pathlib import Path  # 导入 Path 路径对象。

import locale
import os



# 从 pytest 输出字符串里，解析测试代码打印出来的接口响应结果
def parse_response_result(output: str) -> tuple[int | None, str | None]:
    response_status_code = None
    response_content = None

    # 解析响应状态码
    status_match = re.search(r"===RESPONSE_STATUS_CODE===\s*(\d+)", output)
    if status_match:
        response_status_code = int(status_match.group(1))

    # 解析响应内容（多行）
    content_match = re.search(
        r"===RESPONSE_CONTENT_START===\s*(.*?)\s*===RESPONSE_CONTENT_END===",
        output,
        re.DOTALL,
    )
    if content_match:
        response_content = content_match.group(1).strip()

    return response_status_code, response_content

# 安全解码子进程输出：优先按 utf-8 解，如果失败，再尝试 Windows 常见中文编码
def decode_process_output(raw: bytes | None) -> str:
    if not raw:
        return ""

    # 按顺序尝试几种常见编码
    candidate_encodings = [
        "utf-8",
        "gb18030",  # 比 gbk 覆盖更全，中文 Windows 常用兜底
        "gbk",
        locale.getpreferredencoding(False),  # 当前系统首选编码
    ]

    tried = set()
    for enc in candidate_encodings:
        if not enc or enc in tried:
            continue
        tried.add(enc)
        try:
            return raw.decode(enc)
        except Exception:
            continue

    # 最后的兜底：至少不要直接崩
    return raw.decode("utf-8", errors="replace")


# 这个函数的职责 从 pytest 输出字符串中，解析出统计结果
# output: str 表示它接收一个字符串，也就是 pytest 的输出日志。返回值标注：
# tuple[int, int, int] 表示它返回一个三元组，比如：(总数, 通过数, 失败数)
def parse_pytest_result(output: str) -> tuple[int, int, int]:
    # 初始化统计变量
    total_count = 0
    passed_count = 0
    failed_count = 0

    # \d+：一个或多个数字。 ()：把这个数字括起来，后面方便取出来
    # \s+：一个或多个空白字符，比如空格。 passed：字面意思，就是 passed
    # re.search() 返回什么 如果找到，会返回一个匹配对象 Match。如果找不到，会返回 None。
    passed_match = re.search(r"(\d+)\s+passed", output)
    failed_match = re.search(r"(\d+)\s+failed", output)
    error_match = re.search(r"(\d+)\s+error", output)

    # 如果匹配到 passed，就取数字
    if passed_match:
        passed_count = int(passed_match.group(1)) # passed_match.group(1) 取出正则里第 1 个括号捕获到的内容。
    # 如果日志里明确有 failed，优先取 failed
    if failed_match:
        failed_count = int(failed_match.group(1))
    # 如果没有 failed，但有 error，就把 error 当成 failed
    elif error_match:
        failed_count = int(error_match.group(1))

    total_count = passed_count + failed_count
    return total_count, passed_count, failed_count


# 定义一个函数，传入测试文件路径字符串，返回一个字典。
def run_pytest_file(file_path: str) -> dict:
    # 1.把传进来的路径字符串，变成一个规范的绝对路径 Path 对象。
    path_obj = Path(file_path).resolve() # resolve() 会根据当前文件系统，把路径规范化
    # 2.如果这个测试文件根本不存在，就直接抛异常。
    if not path_obj.exists():
        raise FileNotFoundError(f"测试文件不存在: {file_path}")

    # 3.计算 backend 根目录
    backend_dir = path_obj.parent.parent.parent  # backend

    # 4.组装命令
    command = [
        # 这里就是：python -m pytest /backend/app/tests_generated/test_case_3.py -v --tb=short
        sys.executable, # 表示当前 Python 解释器。例如：/xxx/.venv/bin/python
        "-X", "utf8",   # 强制 Python 子进程启用 UTF-8 模式
        "-m",           # -m 的意思是：让 Python 以模块方式运行某个包。
        "pytest",
        str(path_obj),  # 把 Path 对象转成字符串路径，作为 pytest 的目标测试文件
        "-s",  # 关闭 pytest 对 print 输出的捕获，这样 response 打印结果才能稳定进入 stdout
        "-v",           # pytest 的 verbose 模式，也就是更详细输出。
        "--tb=short",   # 这个参数控制 traceback（报错堆栈）的显示长度。tb = traceback。short = 短一点的报错堆栈
    ]

    # 5.真正执行 pytest -> subprocess.run(...)
    # 给子进程显式传编码环境，尽量让 pytest 输出走 UTF-8
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    result = subprocess.run(
        command,
        cwd=str(backend_dir),
        capture_output=True,
        text=False,   # 这里改成 False，先拿原始字节，后面自己解码
        env=env,
    )

    # 6.拿到 pytest 输出
    # subprocess.run(...) 返回的是一个 CompletedProcess 对象。它里面通常有这些重要内容：result.stdout：标准输出 result.stderr：标准错误输出
    stdout = decode_process_output(result.stdout)  # 如果 result.stdout 有内容，就用它，如果是 None 或空，就用空字符串
    stderr = decode_process_output(result.stderr)  # 同理，处理错误输出。
    # 把标准输出和错误输出拼成一份完整日志。 .strip() 的作用 去掉首尾多余空白和换行，日志更干净。
    combined_output = f"{stdout}\n{stderr}".strip()
    # 7.兜底：如果 pytest 没有任何输出
    if not combined_output:
        combined_output = (
            f"pytest 未返回标准输出。\n"
            f"returncode={result.returncode}\n" # 看进程是成功还是失败。
            f"cwd={backend_dir}\n"              # 看是在哪个目录跑的，很多导入问题和目录有关。
            f"command={' '.join(command)}"      # 看实际执行的命令长什么样，排查环境问题很有用。
        )

    # 8.解析 pytest 输出统计结果。调用前面那个解析函数，从总日志里提取出：总数、通过数、失败数
    total_count, passed_count, failed_count = parse_pytest_result(combined_output)
    response_status_code, response_content = parse_response_result(combined_output)

    # 9.根据退出码判断执行结果
    if result.returncode == 0: # 在操作系统里，进程执行结束后会返回一个退出码。通常约定是：0：成功。非 0：失败
        status = "completed"
        run_result = "passed"
    else:
        status = "completed"
        run_result = "failed"
        if total_count == 0:
            total_count = 1   # 这不是 pytest 的原始结果，而是平台层做的业务修正
            failed_count = 1

    # 10.最后返回结构化结果
    return {
        "status": status,
        "result": run_result,
        "total_count": total_count,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "log_content": combined_output,
        "error_message": None if result.returncode == 0 else combined_output,
        "response_status_code": response_status_code,
        "response_content": response_content,
    }

