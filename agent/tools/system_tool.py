import sys
from pathlib import Path

from langchain_core.tools import BaseTool, tool

from agent.skill.skill import SkillContent
from agent.tools.tender_base_tool import query_tender_keyword


@tool
def sys_execute_script_tool(command: str, script_path: str):
    """
    执行脚本（命令）工具，根据操作系统自动适配执行逻辑
    :param command: 指令，例如 'python'、'bash' 或具体参数。若为空，则根据脚本后缀自动选择解释器
    :param script_path: 脚本路径
    """
    import subprocess
    import platform
    import os

    try:
        # 验证脚本路径是否存在
        if not os.path.exists(script_path):
            return f"错误: 脚本文件不存在 - {script_path}"
        
        # 获取操作系统类型
        os_name = platform.system().lower()
        
        # 确定解释器
        interpreter = []
        if command and command.strip():
            # 如果提供了命令，将其作为解释器或前缀
            interpreter = command.strip().split()
        else:
            # 根据脚本后缀自动选择解释器
            ext = os.path.splitext(script_path)[1].lower()
            if ext in ['.py']:
                interpreter = [sys.executable]  # 使用当前 Python 解释器
            elif ext in ['.sh', '.bash'] and os_name != 'windows':
                interpreter = ['bash']
            elif ext in ['.bat', '.cmd'] and os_name == 'windows':
                interpreter = ['cmd', '/c']
            elif ext in ['.ps1'] and os_name == 'windows':
                interpreter = ['powershell', '-ExecutionPolicy', 'Bypass', '-File']
            else:
                # 尝试直接执行（适用于有 shebang 的脚本或可执行文件）
                interpreter = []

        # 构建完整命令
        full_command = interpreter + [script_path]
        
        # 在 Windows 上，如果直接使用列表形式调用 subprocess，某些内置命令可能无法正常工作
        # 但对于脚本执行，通常列表形式更安全
        
        # 执行脚本
        result = subprocess.run(
            full_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
            encoding='utf-8',
            timeout=300  # 设置5分钟超时，防止无限挂起
        )
        
        output = result.stdout
        error_output = result.stderr
        
        if result.returncode != 0:
            return (
                f"脚本执行失败 (返回码: {result.returncode}):\n"
                f"Stdout:\n{output}\n"
                f"Stderr:\n{error_output}"
            )
        
        return f"脚本执行成功:\n{output}" if output else "脚本执行成功，无输出。"

    except subprocess.TimeoutExpired:
        return "错误: 脚本执行超时 (超过5分钟)"
    except Exception as e:
        return f"发生错误: {str(e)}"
   

def _read_text_file(abs_path: Path) -> str:
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(abs_path, "r", encoding="gbk") as f:
            return f.read()


def _file_under_skill_dir(skill_dir: Path, relative: str) -> Path | None:
    """将相对路径安全解析到技能目录内（禁止跳出 skill_dir）。"""
    base = skill_dir.resolve()
    rel = relative.strip().lstrip("/\\")
    if not rel or rel.startswith(".."):
        return None
    candidate = (base / rel).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _resolve_skill_reference_file(skill_name: str, reference_path: str) -> dict | str:
    """
    根据 skill_name 找到技能目录，再匹配参考文件。
    支持本地和 MinIO 两种来源：
    - 本地：返回文件绝对路径 Path 对象
    - MinIO：返回包含内容的字典 {"source": "minio", "content": str, "path": str}
    
    reference_path 为相对路径时依次尝试：技能根目录、references/、ref/ 下同名文件。
    """
    name = (skill_name or "").strip()
    ref_input = (reference_path or "").strip()
    if not name:
        return "错误: skill_name 不能为空"
    if not ref_input:
        return "错误: reference_path 不能为空"

    detail = SkillContent.get_skill(name)
    if detail is None:
        return f"错误: 未知技能 '{name}'，请使用 skills 目录下已有的技能名"

    # 处理绝对路径（仅适用于本地文件系统）
    p_in = Path(ref_input)
    if p_in.is_absolute() and detail.source == "local":
        p = p_in.resolve()
        if not p.is_file():
            return f"错误: 绝对路径不是有效文件 - {ref_input}"
        return p

    # 根据技能来源分别处理
    if detail.source == "minio":
        return _resolve_minio_reference(detail, ref_input)
    else:
        # 默认按本地处理
        return _resolve_local_reference(detail, ref_input)


def _resolve_local_reference(detail, ref_input: str) -> Path | str:
    """解析本地技能的参考文件路径"""
    skill_dir = Path(detail.path).resolve()
    if not skill_dir.is_dir():
        return f"错误: 技能目录不存在 - {skill_dir}"

    for rel in (ref_input, f"references/{ref_input}", f"ref/{ref_input}"):
        found = _file_under_skill_dir(skill_dir, rel.replace("\\", "/"))
        if found is not None:
            return found

    tried = [
        str(skill_dir / ref_input),
        str(skill_dir / "references" / ref_input),
        str(skill_dir / "ref" / ref_input),
    ]
    return (
        f"错误: 在技能 [{detail.name}] 下未找到参考文件 '{ref_input}'。"
        f" 已尝试路径: {tried}"
    )


def _resolve_minio_reference(detail, ref_input: str) -> dict | str:
    """从 MinIO 解析并下载技能的参考文件内容"""
    try:
        from apps import AppContext
        app_ctx = AppContext()
        minio_client = app_ctx.minio_client
        bucket_name = app_ctx.minio_config.get("bucket_name", "skills-bucket")
        
        # MinIO 中的技能路径格式：skills/<skill_name>/<reference_path>
        skill_prefix = f"skills/{detail.name}/"
        
        # 尝试不同的相对路径组合
        candidate_paths = [
            f"{skill_prefix}{ref_input}",
            f"{skill_prefix}references/{ref_input}",
            f"{skill_prefix}ref/{ref_input}",
        ]
        
        for object_path in candidate_paths:
            try:
                # 检查对象是否存在并下载
                response = minio_client.get_object(bucket_name, object_path)
                content_bytes = response.read()
                response.close()
                response.release_conn()
                
                # 尝试 UTF-8 解码，失败则尝试 GBK
                try:
                    content = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    content = content_bytes.decode("gbk")
                
                return {
                    "source": "minio",
                    "content": content,
                    "path": object_path,
                    "skill_name": detail.name
                }
            except Exception:
                # 如果这个路径不存在，尝试下一个
                continue
        
        return (
            f"错误: 在 MinIO 技能 [{detail.name}] 下未找到参考文件 '{ref_input}'。"
            f" 已尝试路径: {candidate_paths}"
        )
        
    except ImportError:
        return "错误: MinIO 客户端未安装，无法加载远程技能参考文件"
    except Exception as e:
        return f"错误: 从 MinIO 加载参考文件失败 - {str(e)}"


@tool
def sys_load_references_tool(skill_name: str, reference_path: str):
    """
    根据技能名解析参考文件的绝对路径并读取文本内容。
    支持从不同来源（如本地 skills 目录）获取技能定义，并根据 reference_path 定位文件：
    1. 若 reference_path 为绝对路径，直接校验并读取。
    2. 若为相对路径，则在技能根目录、references/、ref/ 子目录下查找。
    
    :param skill_name: 技能名称，用于定位技能目录（如 skills/<skill_name>/）。
    :param reference_path: 参考文件的路径。可以是相对于技能目录的路径，也可以是绝对路径。
    """
    try:
        resolved = _resolve_skill_reference_file(skill_name, reference_path)
        if isinstance(resolved, str):
            # 如果返回的是字符串，说明是错误信息
            return resolved
        content = _read_text_file(resolved)
        return f"文件: {resolved}\n\n文件内容:\n{content}"
    except OSError as e:
        return f"错误: 读取文件失败 - {str(e)}"
    except Exception as e:
        return f"发生错误: {str(e)}"

@tool
def sys_install_module_tool(command: str):
    """
    安装python模块工具, 在执行脚本是检查到未安装依赖模块时自动安装
    :param command: 安装依赖模块命令，支持包名（如 'requests'）或完整命令（如 'pip install requests'）
    """
    import subprocess
    import sys
    import platform

    try:
        os_name = platform.system().lower()
        
        # 构建基础命令
        # 优先使用当前 Python 解释器对应的 pip，以确保安装到正确环境
        executable = [sys.executable, "-m", "pip"]
        
        # 解析用户输入的命令
        cmd_parts = []
        if command and command.strip():
            parts = command.strip().split()
            # 如果用户输入了完整命令，尝试提取包名或参数
            # 简单处理：如果包含 'install'，则保留后续部分；否则假设整个字符串是包名
            if 'install' in [p.lower() for p in parts]:
                # 移除 'install' 及其之前的部分，保留包名和选项
                idx = [p.lower() for p in parts].index('install')
                cmd_parts = parts[idx+1:]
            else:
                cmd_parts = parts
        else:
            return "错误: 请提供要安装的模块名称或命令"

        # 构建最终执行命令: python -m pip install <package> [options]
        full_command = executable + ["install"] + cmd_parts

        # 执行安装
        result = subprocess.run(
            full_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
            encoding='utf-8'
        )

        if result.returncode != 0:
            return f"安装失败 (返回码: {result.returncode}):\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}"
        
        return f"安装成功:\n{result.stdout}"

    except Exception as e:
        return f"发生错误: {str(e)}"


def get_registered_system_tools() -> list[BaseTool]:
    """路由层与执行层引用的系统工具列表；新增自定义工具时请在此注册。"""
    return [
        sys_execute_script_tool,
        sys_load_references_tool,
        sys_install_module_tool,
        query_tender_keyword
    ]


def system_tools_by_name() -> dict[str, BaseTool]:
    return {t.name: t for t in get_registered_system_tools()}


def format_system_tools_catalog() -> str:
    """供路由模型阅读的「系统工具」清单。"""
    lines = [
        "【系统工具】（execution_mode=system_tools 时在 system_tool_names 中填写下列名称；可留空表示交给模型从全部系统工具中选择）"
    ]
    for t in get_registered_system_tools():
        desc = (t.description or "").strip().replace("\n", " ")
        max_len = 280
        if len(desc) > max_len:
            desc = desc[: max_len - 3] + "..."
        lines.append(f"- {t.name}: {desc}")
    return "\n".join(lines)
