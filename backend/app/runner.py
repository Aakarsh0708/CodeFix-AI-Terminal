# runner.py
"""
Robust multi-language runner utility.

Provides:
    run_command(cmd, cwd=None, timeout=30) -> (stdout, stderr, returncode, executed_cmd_str)
    is_executable_available(name) -> bool
    run_linter_for_language(file_path, language, timeout=30) -> tuple as above

Supports: python, javascript/node, java, c, cpp/c++.
Designed to work on Windows and Unix-like systems.
"""
import subprocess
import shlex
import shutil
import os
from pathlib import Path
from typing import Tuple, List, Union

CmdType = Union[str, List[str]]


def run_command(cmd: CmdType, cwd=None, timeout=30) -> Tuple[str, str, int, str]:
    """
    Run a command and return (stdout, stderr, returncode, executed_cmd_string).
    Accepts either a list (recommended) or a string.
    On Windows, prefer list to avoid shell-splitting issues.
    """
    executed = ""
    try:
        if isinstance(cmd, list):
            # build a safe display string
            executed = " ".join(shlex.quote(str(a)) for a in cmd)
            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        else:
            # string command
            executed = cmd
            if os.name == "nt":
                # use shell on Windows if user passed a single string
                proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout, shell=True)
            else:
                args = shlex.split(cmd)
                executed = " ".join(shlex.quote(a) for a in args)
                proc = subprocess.run(args, capture_output=True, text=True, cwd=cwd, timeout=timeout)

        return proc.stdout or "", proc.stderr or "", proc.returncode, executed

    except subprocess.TimeoutExpired as e:
        return "", f"TimeoutExpired: process exceeded {timeout} seconds", 124, executed
    except FileNotFoundError as e:
        # common on Windows when executable not present
        return "", f"RunnerError: [WinError 2] The system cannot find the file specified: {e}", 125, executed
    except Exception as e:
        return "", f"RunnerError: {str(e)}", 125, executed


def is_executable_available(name: str) -> bool:
    """Return True if `name` is found on PATH (cross-platform)."""
    return shutil.which(name) is not None


def _make_executable_path(cwd: str, name: str) -> str:
    """
    Return executable filename adjusted for platform.
    Example: _make_executable_path('/tmp', 'a_out') -> '/tmp/a_out' or 'C:\\...\\a_out.exe'
    """
    if os.name == "nt":
        return str(Path(cwd) / f"{name}.exe")
    else:
        return str(Path(cwd) / name)


def run_linter_for_language(file_path: str, language: str, timeout: int = 30) -> Tuple[str, str, int, str]:
    """
    Select a safe default run/diagnose command per language.
    Returns: (stdout, stderr, returncode, executed_cmd)
    - language: one of 'python', 'javascript', 'java', 'c', 'cpp' (case-insensitive)
    Notes:
    - For JS we run node <file> (not 'node -c'); eslint can be used if present.
    - For Python we prefer interpreter; pylint is a fallback for linting.
    """
    p = Path(file_path)
    cwd = str(p.parent)

    lang = (language or "").strip().lower()

    # ---------- Python ----------
    if lang in ("python", "py"):
        python_bin = shutil.which("python") or shutil.which("python3")
        if python_bin:
            cmd = [python_bin, str(p)]
            return run_command(cmd, cwd=cwd, timeout=timeout)
        # fallback to pylint if installed (lint-only)
        if is_executable_available("pylint"):
            cmd = ["pylint", str(p)]
            return run_command(cmd, cwd=cwd, timeout=timeout)
        return "", "No python interpreter or pylint found on PATH.", 125, ""

    # ---------- JavaScript / Node ----------
    elif lang in ("javascript", "js", "node"):
        # prefer node runtime to execute script
        if is_executable_available("node"):
            cmd = ["node", str(p)]
            return run_command(cmd, cwd=cwd, timeout=timeout)
        # fallback linting with eslint if available
        if is_executable_available("eslint"):
            cmd = ["eslint", str(p)]
            return run_command(cmd, cwd=cwd, timeout=timeout)
        return "", "No node or eslint found on PATH.", 125, ""

    # ---------- Java ----------
    elif lang == "java":
        if not is_executable_available("javac"):
            return "", "No javac found on PATH. Please install JDK and add javac to PATH.", 125, ""
        # compile
        compile_cmd = ["javac", str(p)]
        out_c, err_c, rc_c, executed_compile = run_command(compile_cmd, cwd=cwd, timeout=timeout)
        if rc_c != 0:
            return out_c, err_c, rc_c, executed_compile
        # run class by name (filename without .java)
        class_name = p.stem
        if not is_executable_available("java"):
            return out_c, "Compiled but `java` runtime not found on PATH.", 125, executed_compile
        run_cmd = ["java", "-cp", cwd, class_name]
        out_r, err_r, rc_r, executed_run = run_command(run_cmd, cwd=cwd, timeout=timeout)
        executed_full = f"{executed_compile} ; {executed_run}"
        return out_r, err_r, rc_r, executed_full

    # ---------- C / C++ ----------
    elif lang in ("c", "cpp", "c++"):
        is_cpp = lang in ("cpp", "c++")
        compiler = None
        # prefer g++ for C++ and gcc for C
        if is_cpp:
            if is_executable_available("g++"):
                compiler = "g++"
            elif is_executable_available("clang++"):
                compiler = "clang++"
        else:
            if is_executable_available("gcc"):
                compiler = "gcc"
            elif is_executable_available("clang"):
                compiler = "clang"

        if not compiler:
            return "", "No C/C++ compiler found on PATH. Install gcc/g++ or clang.", 125, ""

        # set output executable name inside same dir
        exe_name = "a_out_exec"
        exe_path = _make_executable_path(cwd, exe_name)

        compile_cmd = [compiler, str(p), "-o", exe_path]
        # add C++ standard flag for C++ compilers
        if is_cpp and compiler in ("g++", "clang++"):
            compile_cmd += ["-std=c++17"]

        out_c, err_c, rc_c, executed_compile = run_command(compile_cmd, cwd=cwd, timeout=timeout)
        if rc_c != 0:
            return out_c, err_c, rc_c, executed_compile

        # run compiled executable
        run_cmd = [exe_path]
        out_r, err_r, rc_r, executed_run = run_command(run_cmd, cwd=cwd, timeout=timeout)
        executed_full = f"{executed_compile} ; {executed_run}"
        return out_r, err_r, rc_r, executed_full

    # ---------- Fallback: try to run by file extension ----------
    else:
        # Try a quick fallback for .py files
        if p.suffix == ".py":
            python_bin = shutil.which("python") or shutil.which("python3")
            if python_bin:
                cmd = [python_bin, str(p)]
                return run_command(cmd, cwd=cwd, timeout=timeout)
        return "", f"No runner available for language '{language}'.", 125, ""
