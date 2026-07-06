import os
import subprocess
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from google import genai
from pydantic import BaseModel, Field
import uvicorn

load_dotenv()

app = FastAPI(title="Hyva Transform API", version="2.0.0")

BASE_INSTRUCTION = (
    "You are an automated code-refactoring engine specializing in Magento storefront optimizations. "
    "Your objective is to ingest legacy Magento Luma PHTML templates and output modern, high-performance Hyva Theme structures.\n\n"
    "Strict Architectural Constraints:\n"
    "1. Strip out all legacy script blocks, RequireJS modules, KnockoutJS bindings, and jQuery dependencies completely.\n"
    "2. Restructure the raw HTML semantics, applying native utility classes from Tailwind CSS for all responsive layouts, spacing, and styling.\n"
    "3. Translate all client-side interactive logic (such as toggles, dynamic dropdown visibility, or clicks) into lightweight inline Alpine.js attributes (e.g., x-data, @click, x-show).\n"
    "4. Preserve all native backend PHP security contexts and variable outputs (e.g., $block->escapeHtml(), esc_html__()).\n\n"
    "Output Enforcement: Return ONLY the raw, production-ready template code. Absolutely no Markdown wrapping ticks (```), introductory pleasantries, or explanations."
)

DEFAULT_FILE_PATTERNS = ["*.phtml", "*.xml", "*.js"]
DEFAULT_MAX_FILES = 200
DEFAULT_MAX_FILE_SIZE = 1024 * 1024  # 1 MB


class TransformRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=50000)


class TransformResponse(BaseModel):
    request_id: str
    transformed_template: str
    model: str


class RepoScanRequest(BaseModel):
    repo_path: str
    include_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_FILE_PATTERNS))
    exclude_dirs: list[str] = Field(default_factory=lambda: [".git", "vendor", "node_modules", "pub/static"])
    max_files: int = Field(default=DEFAULT_MAX_FILES, ge=1, le=2000)


class RepoScanResponse(BaseModel):
    request_id: str
    repo_path: str
    total_files: int
    files: list[str]


class RepoConvertRequest(BaseModel):
    repo_path: str
    include_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_FILE_PATTERNS))
    exclude_dirs: list[str] = Field(default_factory=lambda: [".git", "vendor", "node_modules", "pub/static"])
    dry_run: bool = True
    run_tests: bool = False
    test_commands: list[str] = Field(
        default_factory=lambda: [
            "php -v",
            "php bin/magento cache:status",
            "php bin/magento setup:di:compile",
        ]
    )
    max_files: int = Field(default=DEFAULT_MAX_FILES, ge=1, le=2000)
    max_file_size: int = Field(default=DEFAULT_MAX_FILE_SIZE, ge=1024, le=5 * 1024 * 1024)


class FileChange(BaseModel):
    path: str
    changed: bool
    reason: str


class TestResult(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str


class RepoConvertResponse(BaseModel):
    request_id: str
    repo_path: str
    dry_run: bool
    scanned_files: int
    converted_files: int
    changed_files: list[FileChange]
    tests: list[TestResult]


class RepoTestRequest(BaseModel):
    repo_path: str
    commands: list[str]


class RepoTestResponse(BaseModel):
    request_id: str
    repo_path: str
    tests: list[TestResult]


def require_api_token(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    expected_token = os.getenv("MAGENTO_API_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: MAGENTO_API_TOKEN is missing",
        )

    expected_header = f"Bearer {expected_token}"
    if authorization != expected_header:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _allowed_repo_root() -> Path:
    root = os.getenv("MAGENTO_REPO_ROOT", "").strip()
    if not root:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: MAGENTO_REPO_ROOT is missing",
        )
    root_path = Path(root).resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise HTTPException(status_code=500, detail="MAGENTO_REPO_ROOT does not exist")
    return root_path


def _resolve_repo_path(repo_path: str) -> Path:
    root = _allowed_repo_root()
    target = Path(repo_path).resolve()

    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="repo_path is outside MAGENTO_REPO_ROOT") from exc

    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="repo_path not found")

    return target


def _is_in_excluded_dir(path: Path, repo_root: Path, excluded_dirs: set[str]) -> bool:
    relative_parts = path.relative_to(repo_root).parts
    return any(part in excluded_dirs for part in relative_parts)


def _collect_candidate_files(
    repo_root: Path,
    include_patterns: list[str],
    exclude_dirs: list[str],
    max_files: int,
) -> list[Path]:
    excluded = set(exclude_dirs)
    found: list[Path] = []

    for pattern in include_patterns:
        for path in repo_root.rglob(pattern):
            if not path.is_file():
                continue
            if _is_in_excluded_dir(path, repo_root, excluded):
                continue
            found.append(path)

    unique_sorted = sorted(set(found))
    return unique_sorted[:max_files]


def generate_hyva_template(prompt: str) -> str:
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: API_KEY is missing",
        )

    try:
        client = genai.Client(api_key=api_key)
        interaction = client.interactions.create(
            model="gemini-2.5-flash",
            input=BASE_INSTRUCTION + "\n\n" + prompt.strip(),
        )
        return interaction.output_text
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Model error: {str(exc)}")


def _convert_file_contents(content: str, file_path: Path) -> str:
    prompt = (
        f"File path: {file_path.as_posix()}\n"
        "Convert this Magento file for Hyva compatibility while preserving backend variables and escaping context.\n\n"
        f"{content}"
    )
    return generate_hyva_template(prompt)


def _run_commands(repo_root: Path, commands: list[str]) -> list[TestResult]:
    results: list[TestResult] = []

    for command in commands:
        completed = subprocess.run(
            command,
            cwd=str(repo_root),
            shell=True,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        results.append(
            TestResult(
                command=command,
                exit_code=completed.returncode,
                stdout=completed.stdout[-12000:],
                stderr=completed.stderr[-12000:],
            )
        )

    return results


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": app.version}


@app.post("/v1/hyva-transform", response_model=TransformResponse)
def hyva_transform(
    payload: TransformRequest,
    _auth: None = Depends(require_api_token),
) -> TransformResponse:
    transformed = generate_hyva_template(payload.prompt)
    return TransformResponse(
        request_id=str(uuid4()),
        transformed_template=transformed,
        model="gemini-2.5-flash",
    )


@app.post("/api/v1/hyva-transform", response_model=TransformResponse)
def hyva_transform_api_alias(
    payload: TransformRequest,
    _auth: None = Depends(require_api_token),
) -> TransformResponse:
    return hyva_transform(payload, _auth)


@app.post("/v1/repo/scan", response_model=RepoScanResponse)
def repo_scan(
    payload: RepoScanRequest,
    _auth: None = Depends(require_api_token),
) -> RepoScanResponse:
    repo_root = _resolve_repo_path(payload.repo_path)
    files = _collect_candidate_files(
        repo_root,
        payload.include_patterns,
        payload.exclude_dirs,
        payload.max_files,
    )

    return RepoScanResponse(
        request_id=str(uuid4()),
        repo_path=str(repo_root),
        total_files=len(files),
        files=[str(path.relative_to(repo_root).as_posix()) for path in files],
    )


@app.post("/v1/repo/convert", response_model=RepoConvertResponse)
def repo_convert(
    payload: RepoConvertRequest,
    _auth: None = Depends(require_api_token),
) -> RepoConvertResponse:
    repo_root = _resolve_repo_path(payload.repo_path)
    files = _collect_candidate_files(
        repo_root,
        payload.include_patterns,
        payload.exclude_dirs,
        payload.max_files,
    )

    changed_files: list[FileChange] = []
    converted_count = 0

    for file_path in files:
        relative_path = str(file_path.relative_to(repo_root).as_posix())

        if file_path.stat().st_size > payload.max_file_size:
            changed_files.append(
                FileChange(path=relative_path, changed=False, reason="Skipped: file too large")
            )
            continue

        try:
            original = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            changed_files.append(
                FileChange(path=relative_path, changed=False, reason=f"Read error: {str(exc)}")
            )
            continue

        try:
            converted = _convert_file_contents(original, file_path)
        except HTTPException:
            raise
        except Exception as exc:
            changed_files.append(
                FileChange(path=relative_path, changed=False, reason=f"Convert error: {str(exc)}")
            )
            continue

        if converted.strip() == original.strip():
            changed_files.append(FileChange(path=relative_path, changed=False, reason="No change"))
            continue

        converted_count += 1

        if not payload.dry_run:
            try:
                file_path.write_text(converted, encoding="utf-8")
            except Exception as exc:
                changed_files.append(
                    FileChange(path=relative_path, changed=False, reason=f"Write error: {str(exc)}")
                )
                continue

        changed_files.append(
            FileChange(
                path=relative_path,
                changed=True,
                reason="Converted" if not payload.dry_run else "Would convert (dry run)",
            )
        )

    tests: list[TestResult] = []
    if payload.run_tests:
        tests = _run_commands(repo_root, payload.test_commands)

    return RepoConvertResponse(
        request_id=str(uuid4()),
        repo_path=str(repo_root),
        dry_run=payload.dry_run,
        scanned_files=len(files),
        converted_files=converted_count,
        changed_files=changed_files,
        tests=tests,
    )


@app.post("/v1/repo/test", response_model=RepoTestResponse)
def repo_test(
    payload: RepoTestRequest,
    _auth: None = Depends(require_api_token),
) -> RepoTestResponse:
    if not payload.commands:
        raise HTTPException(status_code=400, detail="commands cannot be empty")

    repo_root = _resolve_repo_path(payload.repo_path)
    tests = _run_commands(repo_root, payload.commands)
    return RepoTestResponse(
        request_id=str(uuid4()),
        repo_path=str(repo_root),
        tests=tests,
    )


if __name__ == "__main__":
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )
