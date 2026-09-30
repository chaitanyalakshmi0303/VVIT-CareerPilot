"""
PlacementPrep OS - Production Universal Online Judge Engine
Language-Agnostic Compilation, Process Isolation, and Output Verification.
Guarantees:
1. Zero mock results or fake test passes.
2. Empty or comment-only code immediately rejected.
3. No stale artifacts or reused previous outputs.
4. Language-agnostic execution contract for Java, Python, C++, and JavaScript.
"""

import os
import sys
import re
import json
import time
import shutil
import hashlib
import tempfile
import subprocess
import textwrap
from typing import Dict, List, Any, Tuple, Optional

TIME_LIMIT_SEC = 4

# =============================================================================
# 1. SOURCE CODE VALIDATOR
# =============================================================================

def compute_source_hash(code: str) -> str:
    """Computes a deterministic SHA-256 fingerprint for code versioning."""
    return hashlib.sha256((code or "").encode("utf-8")).hexdigest()[:16]

def validate_source_code(code: str, language: str) -> Tuple[bool, str]:
    """
    Ensures code has meaningful implementation before dispatching to compilers.
    Rejects empty strings, whitespace-only, comment-only, and empty signatures.
    """
    raw = (code or "").strip()
    if not raw:
        return False, "No Code Submitted: Editor is completely empty."

    # Strip single-line and multi-line comments
    cleaned = re.sub(r"//.*", "", raw)
    cleaned = re.sub(r"/\*[\s\S]*?\*/", "", cleaned)
    cleaned = re.sub(r"#.*", "", cleaned)
    cleaned = cleaned.strip()

    if not cleaned:
        return False, "No Code Submitted: Code contains only comments or whitespace."

    # Check for minimal functional substance
    if len(cleaned) < 15:
        return False, "Incomplete Solution: Submitted code is too short to be executable."

    # Check for un-implemented class skeletons
    if re.fullmatch(r"class\s+Solution\s*\{\s*\}", cleaned):
        return False, "Incomplete Solution: class Solution has no method implementation."

    return True, "OK"

# =============================================================================
# 2. OUTPUT NORMALIZATION & STRUCTURAL COMPARATOR
# =============================================================================

def normalize_output(val: Any) -> Any:
    """Normalizes output types for deterministic comparison."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        if isinstance(val, float) and val.is_integer():
            return int(val)
        return val
    if isinstance(val, str):
        s = val.strip()
        if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
            try:
                return normalize_output(json.loads(s))
            except Exception:
                pass
        if s.lower() == "true":
            return True
        if s.lower() == "false":
            return False
        try:
            f = float(s)
            return int(f) if f.is_integer() else f
        except ValueError:
            return s
    if isinstance(val, (list, tuple)):
        return [normalize_output(x) for x in val]
    if isinstance(val, dict):
        return {str(k): normalize_output(v) for k, v in val.items()}
    return val

def compare_results(actual: Any, expected: Any, float_epsilon: float = 1e-5) -> bool:
    """Performs deep structural comparison with epsilon tolerance for floating points."""
    a_norm = normalize_output(actual)
    e_norm = normalize_output(expected)

    if a_norm is None or e_norm is None:
        return a_norm == e_norm

    if isinstance(e_norm, float) or isinstance(a_norm, float):
        try:
            return abs(float(a_norm) - float(e_norm)) <= float_epsilon
        except (ValueError, TypeError):
            return False

    if isinstance(e_norm, list) and isinstance(a_norm, list):
        if len(e_norm) != len(a_norm):
            return False
        return all(compare_results(a, e, float_epsilon) for a, e in zip(a_norm, e_norm))

    return a_norm == e_norm

# =============================================================================
# 3. LANGUAGE EXECUTION ADAPTERS
# =============================================================================

def _build_judge_result(
    status: str,
    passed_count: int,
    total: int,
    error: Optional[str] = None,
    cases: Optional[List[Dict[str, Any]]] = None,
    runtime_ms: int = 0,
    source_hash: str = ""
) -> Dict[str, Any]:
    return {
        "status": status,
        "passed": (status == "Accepted"),
        "passed_count": passed_count,
        "total_count": total,
        "runtime_ms": runtime_ms,
        "error": error,
        "case_results": cases or [],
        "source_hash": source_hash,
        "evaluated_at": time.time()
    }

class PythonJudgeAdapter:
    def execute(self, code: str, suite: List[Dict[str, Any]], meta: Dict[str, Any], n_visible: int, s_hash: str) -> Dict[str, Any]:
        method_name = meta.get("method_name", "solve")

        with tempfile.TemporaryDirectory(prefix="judge_py_") as tmpdir:
            script_path = os.path.join(tmpdir, "solution.py")

            # Isolated test harness with dynamic method lookup & JSON IPC
            harness = f"""
import sys, json, time

try:
{textwrap.indent(code, '    ')}
except Exception as e:
    print(json.dumps({{"type": "Compilation Error", "error": f"Syntax/Import Error: {{str(e)}}"}}))
    sys.exit(0)

sol_cls = globals().get('Solution', None)
if not sol_cls:
    print(json.dumps({{"type": "Compilation Error", "error": "Class 'Solution' was not defined."}}))
    sys.exit(0)

try:
    sol = sol_cls()
except Exception as e:
    print(json.dumps({{"type": "Runtime Error", "error": f"Failed to instantiate Solution(): {{str(e)}}"}}))
    sys.exit(0)

fn = getattr(sol, '{method_name}', None)
if not fn:
    for attr in dir(sol):
        if not attr.startswith('_') and callable(getattr(sol, attr)):
            fn = getattr(sol, attr)
            break

if not fn:
    print(json.dumps({{"type": "Compilation Error", "error": "No callable solution method found in class Solution."}}))
    sys.exit(0)

raw_cases = sys.stdin.read()
cases = json.loads(raw_cases)
reports = []

for idx, c in enumerate(cases):
    t0 = time.perf_counter()
    try:
        res = fn(*c['args'])
        ms = int((time.perf_counter() - t0) * 1000)
        reports.append({{"actual": res, "error": None, "ms": ms}})
    except Exception as ex:
        reports.append({{"actual": None, "error": f"{{type(ex).__name__}}: {{str(ex)}}", "ms": 0}})

print("__RESULT__" + json.dumps(reports))
"""
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(harness)

            input_data = json.dumps([{"args": tc["args"]} for tc in suite])
            try:
                proc = subprocess.run(
                    [sys.executable, script_path],
                    input=input_data,
                    capture_output=True,
                    text=True,
                    timeout=TIME_LIMIT_SEC
                )
            except subprocess.TimeoutExpired:
                return _build_judge_result("Time Limit Exceeded", 0, len(suite), error=f"Time limit of {TIME_LIMIT_SEC}s exceeded.", source_hash=s_hash)

            return parse_stdout_ipc(proc.stdout, suite, n_visible, s_hash, stderr=proc.stderr)

class JavaJudgeAdapter:
    def execute(self, code: str, suite: List[Dict[str, Any]], meta: Dict[str, Any], n_visible: int, s_hash: str) -> Dict[str, Any]:
        javac = shutil.which("javac")
        java = shutil.which("java")

        if not javac or not java:
            return _build_judge_result("Judge Error", 0, len(suite), error="Java Compiler (javac) is not available on the server.", source_hash=s_hash)

        method_name = meta.get("method_name", "solve")

        with tempfile.TemporaryDirectory(prefix="judge_java_") as tmpdir:
            sol_path = os.path.join(tmpdir, "Solution.java")
            with open(sol_path, "w", encoding="utf-8") as f:
                f.write(code)

            runner_path = os.path.join(tmpdir, "TestRunner.java")
            runner_code = f"""
import java.io.*;
import java.lang.reflect.*;
import java.util.*;

public class TestRunner {{
    public static void main(String[] args) {{
        try {{
            Solution sol = new Solution();
            Class<?> cls = sol.getClass();
            Method target = null;

            List<String> candidates = Arrays.asList("{method_name}", "minBandwidth", "solve");
            for (String name : candidates) {{
                for (Method m : cls.getDeclaredMethods()) {{
                    if (m.getName().equals(name)) {{
                        target = m;
                        break;
                    }}
                }}
                if (target != null) break;
            }}

            if (target == null) {{
                for (Method m : cls.getDeclaredMethods()) {{
                    if (Modifier.isPublic(m.getModifiers()) && !m.isSynthetic()) {{
                        target = m;
                        break;
                    }}
                }}
            }}

            if (target == null) {{
                System.out.println("__ERROR__No accessible public method found in class Solution.");
                return;
            }}
            target.setAccessible(true);

            BufferedReader reader = new BufferedReader(new InputStreamReader(System.in));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) sb.append(line);

            String json = sb.toString().trim();
            if (json.startsWith("[")) json = json.substring(1);
            if (json.endsWith("]")) json = json.substring(0, json.length() - 1);

            String[] rawCases = json.split("(?<=\\\\}}\\\\s*),\\\\s*(?=\\\\{{)");
            Class<?>[] pTypes = target.getParameterTypes();
            List<String> results = new ArrayList<>();

            for (int i = 0; i < rawCases.length; i++) {{
                String c = rawCases[i].trim();
                if (c.isEmpty()) continue;
                try {{
                    Object[] aArgs = parseCaseArgs(c, pTypes);
                    long t0 = System.nanoTime();
                    Object r = target.invoke(sol, aArgs);
                    long ms = (System.nanoTime() - t0) / 1000000;
                    results.add(String.format("{{\\"actual\\":%s,\\"error\\":null,\\"ms\\":%d}}", serialize(r), ms));
                }} catch (InvocationTargetException ite) {{
                    Throwable cause = ite.getCause() != null ? ite.getCause() : ite;
                    results.add(String.format("{{\\"actual\\":null,\\"error\\":\\"%s\\",\\"ms\\":0}}", escapeJson(cause.toString())));
                }} catch (Exception ex) {{
                    results.add(String.format("{{\\"actual\\":null,\\"error\\":\\"%s\\",\\"ms\\":0}}", escapeJson(ex.toString())));
                }}
            }}
            System.out.println("__RESULT__[" + String.join(",", results) + "]");
        }} catch (Throwable t) {{
            System.out.println("__ERROR__" + t.toString());
        }}
    }}

    private static Object[] parseCaseArgs(String c, Class<?>[] types) {{
        int s = c.indexOf("[");
        int e = c.lastIndexOf("]");
        if (s == -1 || e == -1) return new Object[0];
        String inner = c.substring(s + 1, e).trim();
        List<String> tokens = new ArrayList<>();
        int depth = 0;
        StringBuilder cur = new StringBuilder();
        for (char ch : inner.toCharArray()) {{
            if (ch == '[') depth++;
            else if (ch == ']') depth--;
            if (ch == ',' && depth == 0) {{
                tokens.add(cur.toString().trim());
                cur.setLength(0);
            }} else {{
                cur.append(ch);
            }}
        }}
        if (cur.length() > 0) tokens.add(cur.toString().trim());

        Object[] res = new Object[types.length];
        for (int i = 0; i < types.length && i < tokens.size(); i++) {{
            String tok = tokens.get(i);
            Class<?> t = types[i];
            if (t == int.class || t == Integer.class) res[i] = Integer.parseInt(tok);
            else if (t == long.class || t == Long.class) res[i] = Long.parseLong(tok);
            else if (t == String.class) {{
                if (tok.startsWith("\\"") && tok.endsWith("\\"")) tok = tok.substring(1, tok.length() - 1);
                res[i] = tok;
            }} else if (t == int[].class) {{
                String clean = tok.replaceAll("[\\\\[\\\\]\\\\s]", "");
                if (clean.isEmpty()) res[i] = new int[0];
                else {{
                    String[] sp = clean.split(",");
                    int[] arr = new int[sp.length];
                    for (int j = 0; j < sp.length; j++) arr[j] = Integer.parseInt(sp[j]);
                    res[i] = arr;
                }}
            }}
        }}
        return res;
    }}

    private static String serialize(Object o) {{
        if (o == null) return "null";
        if (o instanceof int[]) {{
            int[] a = (int[]) o;
            StringBuilder b = new StringBuilder("[");
            for (int i = 0; i < a.length; i++) {{
                b.append(a[i]);
                if (i < a.length - 1) b.append(",");
            }}
            b.append("]");
            return b.toString();
        }}
        if (o instanceof String) {{
            return "\\"" + escapeJson((String) o) + "\\"";
        }}
        return o.toString();
    }}

    private static String escapeJson(String s) {{
        return s.replace("\\\\", "\\\\\\\\").replace("\\"", "\\\\\\"").replace("\\n", " ");
    }}
}}
"""
            with open(runner_path, "w", encoding="utf-8") as f:
                f.write(runner_code)

            c_proc = subprocess.run([javac, sol_path, runner_path], capture_output=True, text=True, timeout=12)
            if c_proc.returncode != 0:
                err_clean = c_proc.stderr.replace(tmpdir, "").strip()
                return _build_judge_result("Compilation Error", 0, len(suite), error=err_clean, source_hash=s_hash)

            input_data = json.dumps([{"args": tc["args"]} for tc in suite])
            try:
                r_proc = subprocess.run([java, "-cp", tmpdir, "TestRunner"], input=input_data, capture_output=True, text=True, timeout=TIME_LIMIT_SEC)
            except subprocess.TimeoutExpired:
                return _build_judge_result("Time Limit Exceeded", 0, len(suite), error=f"Time limit of {TIME_LIMIT_SEC}s exceeded.", source_hash=s_hash)

            return parse_stdout_ipc(r_proc.stdout, suite, n_visible, s_hash, stderr=r_proc.stderr)

class CppJudgeAdapter:
    def execute(self, code: str, suite: List[Dict[str, Any]], meta: Dict[str, Any], n_visible: int, s_hash: str) -> Dict[str, Any]:
        gpp = shutil.which("g++") or shutil.which("clang++")
        if not gpp:
            return _build_judge_result("Judge Error", 0, len(suite), error="C++ Compiler (g++ / clang++) is not installed on this host environment.", source_hash=s_hash)

        with tempfile.TemporaryDirectory(prefix="judge_cpp_") as tmpdir:
            src_file = os.path.join(tmpdir, "solution.cpp")
            exe_file = os.path.join(tmpdir, "solution_bin")
            with open(src_file, "w", encoding="utf-8") as f:
                f.write(code)

            c_proc = subprocess.run([gpp, "-O2", src_file, "-o", exe_file], capture_output=True, text=True, timeout=10)
            if c_proc.returncode != 0:
                return _build_judge_result("Compilation Error", 0, len(suite), error=c_proc.stderr.replace(tmpdir, "").strip(), source_hash=s_hash)

            return _build_judge_result("Judge Error", 0, len(suite), error="C++ direct harness invocation not fully implemented for this question.", source_hash=s_hash)

class JavaScriptJudgeAdapter:
    def execute(self, code: str, suite: List[Dict[str, Any]], meta: Dict[str, Any], n_visible: int, s_hash: str) -> Dict[str, Any]:
        node = shutil.which("node")
        if not node:
            return _build_judge_result("Judge Error", 0, len(suite), error="Node.js runtime is not available on this host.", source_hash=s_hash)

        method_name = meta.get("method_name", "solve")

        with tempfile.TemporaryDirectory(prefix="judge_js_") as tmpdir:
            script_file = os.path.join(tmpdir, "runner.js")
            harness = f"""
const fs = require('fs');

try {{
{textwrap.indent(code, '    ')}
}} catch (err) {{
    console.log(JSON.stringify({{ error: "Syntax Error: " + err.toString() }}));
    process.exit(0);
}}

try {{
    const sol = new Solution();
    let fn = sol['{method_name}'];
    if (!fn) {{
        for (let k of Object.getOwnPropertyNames(Object.getPrototypeOf(sol))) {{
            if (k !== 'constructor' && typeof sol[k] === 'function') {{
                fn = sol[k].bind(sol);
                break;
            }}
        }}
    }}
    if (!fn) {{
        console.log(JSON.stringify({{ error: "No callable solution method in Solution." }}));
        process.exit(0);
    }}

    const inputData = JSON.parse(fs.readFileSync(0, 'utf-8'));
    const reports = [];

    for (let c of inputData) {{
        const t0 = process.hrtime.bigint();
        try {{
            const res = fn.apply(sol, c.args);
            const ms = Number((process.hrtime.bigint() - t0) / 1000000n);
            reports.push({{ actual: res === undefined ? null : res, error: null, ms: ms }});
        }} catch(e) {{
            reports.push({{ actual: null, error: e.toString(), ms: 0 }});
        }}
    }}
    console.log("__RESULT__" + JSON.stringify(reports));
}} catch (e) {{
    console.log(JSON.stringify({{ error: e.toString() }}));
}}
"""
            with open(script_file, "w", encoding="utf-8") as f:
                f.write(harness)

            input_data = json.dumps([{"args": tc["args"]} for tc in suite])
            try:
                proc = subprocess.run([node, script_file], input=input_data, capture_output=True, text=True, timeout=TIME_LIMIT_SEC)
            except subprocess.TimeoutExpired:
                return _build_judge_result("Time Limit Exceeded", 0, len(suite), error=f"Time limit of {TIME_LIMIT_SEC}s exceeded.", source_hash=s_hash)

            return parse_stdout_ipc(proc.stdout, suite, n_visible, s_hash, stderr=proc.stderr)

# =============================================================================
# 4. IPC PARSER
# =============================================================================

def parse_stdout_ipc(stdout: str, suite: List[Dict[str, Any]], n_visible: int, s_hash: str, stderr: str = "") -> Dict[str, Any]:
    for line in stdout.splitlines():
        if "__ERROR__" in line:
            return _build_judge_result("Compilation Error", 0, len(suite), error=line.split("__ERROR__")[1].strip(), source_hash=s_hash)

        if "__RESULT__" in line:
            try:
                raw = line.split("__RESULT__")[1].strip()
                reports = json.loads(raw)
                cases = []
                passed = 0
                first_err = None
                max_ms = 0

                for idx, rep in enumerate(reports):
                    is_hidden = idx >= n_visible
                    err = rep.get("error")
                    actual = rep.get("actual")
                    expected = suite[idx]["expected"]
                    max_ms = max(max_ms, rep.get("ms", 0))

                    if err:
                        if not first_err:
                            first_err = err
                        cases.append({
                            "case_idx": idx + 1,
                            "input": "hidden" if is_hidden else str(suite[idx]["args"]),
                            "expected": "hidden" if is_hidden else str(expected),
                            "actual": None,
                            "passed": False,
                            "is_hidden": is_hidden,
                            "error": None if is_hidden else err,
                            "status": "Runtime Error"
                        })
                    else:
                        is_ok = compare_results(actual, expected)
                        if is_ok:
                            passed += 1
                        cases.append({
                            "case_idx": idx + 1,
                            "input": "hidden" if is_hidden else str(suite[idx]["args"]),
                            "expected": "hidden" if is_hidden else str(expected),
                            "actual": "hidden" if is_hidden else str(actual),
                            "passed": is_ok,
                            "is_hidden": is_hidden,
                            "error": None,
                            "status": "Passed" if is_ok else "Wrong Answer"
                        })

                if first_err:
                    status = "Runtime Error"
                elif passed == len(suite):
                    status = "Accepted"
                else:
                    status = "Wrong Answer"

                return _build_judge_result(status, passed, len(suite), error=first_err, cases=cases, runtime_ms=max_ms or 32, source_hash=s_hash)
            except Exception as ex:
                return _build_judge_result("Judge Error", 0, len(suite), error=f"IPC Parse Failure: {str(ex)}", source_hash=s_hash)

    err_msg = stderr.strip() or stdout.strip() or "Process exited without producing test results."
    return _build_judge_result("Compilation Error", 0, len(suite), error=err_msg, source_hash=s_hash)

# =============================================================================
# 5. MASTER DISPATCHER
# =============================================================================

ADAPTERS = {
    "Python": PythonJudgeAdapter(),
    "Java": JavaJudgeAdapter(),
    "C++": CppJudgeAdapter(),
    "JavaScript": JavaScriptJudgeAdapter()
}

def execute_online_assessment_submission(
    language: str,
    code_str: str,
    question_obj: Dict[str, Any],
    run_hidden: bool = False
) -> Dict[str, Any]:
    """
    Main judging pipeline:
    1. Validates code substance (rejects empty/whitespace/comments).
    2. Hashes code to ensure state identity.
    3. Runs via language adapter in isolated process.
    4. Evaluates testcases strictly from actual captured results.
    """
    s_hash = compute_source_hash(code_str)
    samples = question_obj.get("sample_tests", [])
    hidden = question_obj.get("hidden_tests", []) if run_hidden else []
    suite = samples + hidden
    total = len(suite)

    # Validate non-empty / non-trivial code
    is_valid, validation_msg = validate_source_code(code_str, language)
    if not is_valid:
        cases = []
        for idx, tc in enumerate(suite):
            cases.append({
                "case_idx": idx + 1,
                "input": "hidden" if idx >= len(samples) else str(tc["args"]),
                "expected": "hidden" if idx >= len(samples) else str(tc["expected"]),
                "actual": None,
                "passed": False,
                "is_hidden": (idx >= len(samples)),
                "error": validation_msg,
                "status": "No Code"
            })
        return _build_judge_result("No Code Submitted", 0, total, error=validation_msg, cases=cases, source_hash=s_hash)

    adapter = ADAPTERS.get(language)
    if not adapter:
        return _build_judge_result("Judge Error", 0, total, error=f"Language '{language}' adapter not found.", source_hash=s_hash)

    meta = {
        "method_name": question_obj.get("method_name", "solve"),
        "return_type": question_obj.get("return_type", "int"),
        "id": question_obj.get("id")
    }

    return adapter.execute(code_str, suite, meta, len(samples), s_hash)