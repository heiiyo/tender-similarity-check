from pathlib import Path

from langchain_core.tools import BaseTool, tool

from agent.skill.skill import SkillContent


@tool
def sys_execute_script_tool(command: str, script_path: str):
    """
    执行脚本（命令）工具，根据操作系统自动适配执行逻辑
    :param command: 指令，例如 'python'、'bash' 或具体参数。若为空，则根据脚本后缀自动选择解释器
    :param script_path: 脚本路径
    """
    import subprocess
    import sys
    import os
    import platform

    try:
        # 检查脚本路径是否存在
        if not os.path.exists(script_path):
            return f"错误: 脚本路径不存在 - {script_path}"

        # 获取操作系统类型
        os_name = platform.system().lower()  # 'windows', 'linux', 'darwin', etc.
        
        # 获取脚本绝对路径和工作目录
        abs_script_path = os.path.abspath(script_path)
        work_dir = os.path.dirname(abs_script_path)
        
        # 确定默认解释器
        file_ext = os.path.splitext(script_path)[1].lower()
        
        # 如果 command 为空，根据文件扩展名和操作系统推断解释器
        if not command or command.strip() == "":
            if file_ext in ['.py']:
                full_command = [sys.executable, abs_script_path]
            elif file_ext in ['.sh', '.bash']:
                if os_name == 'windows':
                    # Windows 上尝试使用 Git Bash 或 WSL，如果不存在则报错或提示
                    # 这里简单处理，尝试使用 sh (如果安装了 Git for Windows)
                    full_command = ['sh', abs_script_path]
                else:
                    full_command = ['bash', abs_script_path]
            elif file_ext in ['.bat', '.cmd']:
                if os_name == 'windows':
                    full_command = ['cmd', '/c', abs_script_path]
                else:
                    return f"错误: 在 {os_name} 系统上无法直接执行 .bat/.cmd 脚本"
            elif file_ext in ['.ps1']:
                if os_name == 'windows':
                    full_command = ['powershell', '-ExecutionPolicy', 'Bypass', '-File', abs_script_path]
                else:
                    return f"错误: 在 {os_name} 系统上无法直接执行 .ps1 脚本"
            elif file_ext in ['.js']:
                full_command = ['node', abs_script_path]
            else:
                # 未知类型，默认尝试用当前 python 解释器或者 shell
                # 为了安全，对于无后缀或未知后缀，如果没有指定 command，拒绝执行或默认用 python
                full_command = [sys.executable, abs_script_path]
        else:
            # 用户指定了 command
            cmd_parts = command.split()
            executable = cmd_parts[0].lower()
            
            # 安全检查：白名单机制
            allowed_executables = {
                'python', 'python3', 
                'node', 'npm', 
                'bash', 'sh', 'zsh', 
                'cmd', 'powershell', 'pwsh',
                'pip', 'pip3'
            }
            
            # 判断是否允许执行
            is_allowed = False
            if executable in allowed_executables:
                is_allowed = True
            elif os.path.isabs(executable) and os.path.isfile(executable):
                # 允许绝对路径的可执行文件
                is_allowed = True
            elif os_name == 'windows' and executable in ['cmd.exe', 'powershell.exe']:
                 is_allowed = True
            
            if not is_allowed:
                return f"错误: 不允许执行的命令 '{executable}'。为了安全，仅支持常见解释器或绝对路径。"

            # 构建完整命令
            # 特殊处理 Windows 下的 cmd 和 powershell
            if os_name == 'windows':
                if executable in ['cmd', 'cmd.exe']:
                    # cmd /c "command args script"
                    # 这里假设 command 是 'cmd'，我们需要构造 'cmd /c script' 或者保留用户参数
                    # 如果用户传的是 'cmd /c'，则 cmd_parts 已经是 ['cmd', '/c']
                    if '/c' not in [p.lower() for p in cmd_parts]:
                        full_command = ['cmd', '/c'] + cmd_parts[1:] + [abs_script_path]
                    else:
                        full_command = cmd_parts + [abs_script_path]
                elif executable in ['powershell', 'powershell.exe', 'pwsh']:
                    if '-file' not in [p.lower() for p in cmd_parts]:
                        full_command = cmd_parts + ['-File', abs_script_path]
                    else:
                        full_command = cmd_parts + [abs_script_path]
                else:
                    full_command = cmd_parts + [abs_script_path]
            else:
                # Linux/Mac
                full_command = cmd_parts + [abs_script_path]

        # 执行命令
        # shell=True 在某些情况下需要，但为了安全尽量使用列表形式执行
        # 对于 cmd /c 这种结构，subprocess.run 列表形式通常也能工作，但有时需要 shell=True
        # 这里保持列表形式，大多数情况足够
        
        result = subprocess.run(
            full_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
            cwd=work_dir,
            # 在 Windows 上，如果启动新进程，可能需要 creationflags 来隐藏窗口等，这里保持默认
        )

        output = result.stdout
        error = result.stderr

        if result.returncode != 0:
            return f"执行失败 (返回码: {result.returncode}):\nStdout:\n{output}\nStderr:\n{error}"
        
        return f"执行成功:\n{output}"

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


def _resolve_skill_reference_file(skill_name: str, reference_path: str) -> Path | str:
    """
    根据 skill_name 找到 skills/<name>/，再匹配参考文件得到绝对路径。
    reference_path 为相对路径时依次尝试：技能根目录、references/、ref/ 下同名文件。
    """
    name = (skill_name or "").strip()
    ref_input = (reference_path or "").strip()
    if not name:
        return "错误: skill_name 不能为空"
    if not ref_input:
        return "错误: reference_path 不能为空"

    p_in = Path(ref_input)
    if p_in.is_absolute():
        p = p_in.resolve()
        if not p.is_file():
            return f"错误: 绝对路径不是有效文件 - {ref_input}"
        return p

    detail = SkillContent.get_skill(name)
    if detail is None:
        return f"错误: 未知技能 '{name}'，请使用 skills 目录下已有的技能名"

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
        f"错误: 在技能 [{name}] 下未找到参考文件 '{ref_input}'。"
        f" 已尝试路径: {tried}"
    )


@tool
def sys_load_references_tool(skill_name: str, reference_path: str):
    """
    根据技能名解析参考文件的绝对路径并读取文本内容。
    先匹配技能目录 project/skills/<skill_name>/，再将 reference_path 解析为该目录下的文件：
    支持相对路径（如 notes.md、references/foo.txt）；若为绝对路径则在校验为文件后直接读取。

    :param skill_name: skills 目录下的技能文件夹名，与 SKILL.md 中 name 一致。
    :param reference_path: 相对技能目录的参考文件路径，或已有文件的绝对路径。
    """
    try:
        resolved = _resolve_skill_reference_file(skill_name, reference_path)
        if isinstance(resolved, str):
            return resolved

        content = _read_text_file(resolved)
        print(f"sys_load_references_tool: {content}")
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
            text=True
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
