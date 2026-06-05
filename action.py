import argparse
import os
import subprocess
import sys
import tempfile
from typing import Iterable, List


def run_cmd(
    args: List[str],
    cwd: str | None = None,
    check: bool = False,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=capture_output,
    )


def get_changed_files(
    base_ref: str,
    exclude_dirs: Iterable[str],
    analyze_all: bool,
) -> List[str]:
    workspace = os.environ.get("GITHUB_WORKSPACE", os.getcwd())

    if analyze_all:
        matched_files: List[str] = []
        for root, dirs, files in os.walk(workspace):
            if ".git" in dirs:
                dirs.remove(".git")
            rel_root = os.path.relpath(root, workspace)
            for filename in files:
                if not filename.endswith((".cpp", ".hpp", ".c", ".h")):
                    continue
                path = os.path.normpath(os.path.join(rel_root, filename))
                if path.startswith("."):
                    path = path[2:] if path.startswith("./") else path.lstrip("./")
                matched_files.append(path)
    else:
        diff_args = [
            "git",
            "diff",
            "--name-only",
            f"origin/{base_ref}...HEAD",
            "--",
            "*.cpp",
            "*.hpp",
            "*.c",
            "*.h",
        ]
        result = run_cmd(diff_args, cwd=workspace, capture_output=True)
        stdout = result.stdout or ""
        matched_files = [line.strip() for line in stdout.splitlines() if line.strip()]

    exclude_prefixes = [d.rstrip("/") + "/" for d in exclude_dirs if d]
    filtered_files: List[str] = []
    for path in matched_files:
        if any(path.startswith(prefix) for prefix in exclude_prefixes):
            continue
        filtered_files.append(path)

    return filtered_files


def count_issues_from_output(output: str) -> int:
    issues = 0
    for line in output.splitlines():
        if "warning:" in line or "error:" in line:
            issues += 1
    return issues


def write_output(name: str, value: str) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run native clang-tidy analysis.")
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--exclude", default="")
    parser.add_argument("--clang-tidy-version", required=True)
    parser.add_argument("--base-ref", required=True)
    args = parser.parse_args()

    workspace = os.environ.get("GITHUB_WORKSPACE", os.getcwd())

    run_cmd(
        ["clang-tidy-" + args.clang_tidy_version, "--version"],
        cwd=workspace,
        check=True,
    )

    run_cmd(
        ["git", "config", "--global", "--add", "safe.directory", workspace],
        cwd=workspace,
    )
    run_cmd(["git", "fetch", "origin", args.base_ref], cwd=workspace)

    diff_config_args = [
        "git",
        "diff",
        "--name-only",
        f"origin/{args.base_ref}...HEAD",
        "--",
        "**/.clang-tidy",
    ]
    diff_config_result = run_cmd(
        diff_config_args,
        cwd=workspace,
        capture_output=True,
    )
    clang_tidy_changed = bool(diff_config_result.stdout and diff_config_result.stdout.strip())

    if clang_tidy_changed:
        print("::notice::.clang-tidy configuration changed, analyzing all source files")

    exclude_dirs = args.exclude.split()
    changed_files = get_changed_files(
        base_ref=args.base_ref,
        exclude_dirs=exclude_dirs,
        analyze_all=clang_tidy_changed,
    )

    if not changed_files:
        write_output("total_comments", "0")
        return 0

    comments_fd, comments_path = tempfile.mkstemp()
    os.close(comments_fd)

    total_issues = 0
    clang_tidy_executable = "clang-tidy-" + args.clang_tidy_version

    try:
        for path in changed_files:
            file_path = os.path.join(workspace, path)
            if not os.path.isfile(file_path):
                continue

            print(f"Analyzing {path}...")
            with tempfile.NamedTemporaryFile(mode="w+", delete=False, encoding="utf-8") as tmp_file:
                tmp_name = tmp_file.name

            try:
                result = subprocess.run([
                        clang_tidy_executable,
                        path,
                        "-p",
                        args.build_dir,
                        "--format-style=file",
                    ],
                    cwd=workspace,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )

                output = result.stdout or ""
                sys.stdout.write(output)
                with open(tmp_name, "w", encoding="utf-8") as tmp_file:
                    tmp_file.write(output)

                if result.returncode == 0:
                    issues = count_issues_from_output(output)
                    total_issues += issues
                    with open(comments_path, "a", encoding="utf-8") as comments_file:
                        comments_file.write(output)
                else:
                    print(f"::error::Failed to analyze {path}")
                    total_issues += 1
            finally:
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass

        write_output("total_comments", str(total_issues))

        if os.path.isfile(comments_path) and os.path.getsize(comments_path) > 0:
            print("::group::Clang-tidy Analysis Results")
            with open(comments_path, "r", encoding="utf-8") as comments_file:
                sys.stdout.write(comments_file.read())
            print("::endgroup::")

        if total_issues > 0:
            print(f"::error::Found {total_issues} clang-tidy issues")
        else:
            print("No clang-tidy issues found")
    finally:
        try:
            os.remove(comments_path)
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    raise sys.exit(main())
