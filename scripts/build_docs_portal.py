#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import generate_docs_site as docs_site
from controller_automation_toolkit import emit_cli_error, repo_path


REPO_ROOT = repo_path()
MKDOCS_CONFIG_PATH = repo_path("mkdocs.yml")
DEFAULT_GENERATED_DIR = repo_path("docs", "site-generated")
DEFAULT_OUTPUT_DIR = repo_path("build", "docs-portal")
PUBLISHED_ARTIFACT_SCAN = repo_path("scripts", "published_artifact_secret_scan.py")
EXPECTED_SITE_ARTIFACTS = (
    Path("index.html"),
    Path("services", "keycloak", "index.html"),
    Path("reference", "ports", "index.html"),
    Path("pagefind", "pagefind-entry.json"),
    Path("pagefind", "pagefind-ui.js"),
    Path("pagefind", "pagefind-ui.css"),
)


def run_command(argv: list[str]) -> None:
    subprocess.run(argv, cwd=REPO_ROOT, check=True)


def mkdocs_config_for_generated_dir(generated_dir: Path) -> tuple[Path, Path | None]:
    if generated_dir.resolve() == DEFAULT_GENERATED_DIR.resolve():
        return MKDOCS_CONFIG_PATH, None

    mkdocs_config = MKDOCS_CONFIG_PATH.read_text(encoding="utf-8")
    rewritten = mkdocs_config.replace(
        f"docs_dir: {DEFAULT_GENERATED_DIR.relative_to(REPO_ROOT).as_posix()}",
        f"docs_dir: {generated_dir.as_posix()}",
        1,
    )
    if rewritten == mkdocs_config:
        raise ValueError(f"unable to rewrite docs_dir in {MKDOCS_CONFIG_PATH}")

    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="lv3-mkdocs-",
        suffix=".yml",
        dir=REPO_ROOT,
        delete=False,
    )
    with temp_file:
        temp_file.write(rewritten)
    return Path(temp_file.name), Path(temp_file.name)


def validate_built_site(output_dir: Path) -> None:
    missing = [path for path in EXPECTED_SITE_ARTIFACTS if not (output_dir / path).exists()]
    if missing:
        details = ", ".join(str(path) for path in missing)
        raise ValueError(f"missing built docs portal artifacts: {details}")


def should_scan_output(output_dir: Path) -> bool:
    try:
        output_dir.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return False
    return True


def build_docs_portal(
    *,
    generated_dir: Path,
    output_dir: Path,
    openapi_url: str | None,
    pagefind_root_selector: str,
) -> None:
    docs_site.render_site(generated_dir, openapi_url=openapi_url)
    docs_site.validate_site(generated_dir)

    mkdocs_config_path, temp_config_path = mkdocs_config_for_generated_dir(generated_dir)
    try:
        run_command(
            [
                sys.executable,
                "-m",
                "mkdocs",
                "build",
                "--strict",
                "--config-file",
                str(mkdocs_config_path),
                "--site-dir",
                str(output_dir),
            ]
        )
    finally:
        if temp_config_path is not None:
            temp_config_path.unlink(missing_ok=True)

    run_command(
        [
            sys.executable,
            "-m",
            "pagefind",
            "--site",
            str(output_dir),
            "--root-selector",
            pagefind_root_selector,
        ]
    )
    validate_built_site(output_dir)
    if should_scan_output(output_dir):
        run_command(
            [
                sys.executable,
                str(PUBLISHED_ARTIFACT_SCAN),
                "--repo-root",
                str(REPO_ROOT),
                "--path",
                str(output_dir / "pagefind"),
            ]
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the docs portal and its Pagefind search bundle.")
    parser.add_argument(
        "--generated-dir",
        default=str(DEFAULT_GENERATED_DIR),
        help="Where the generated MkDocs source tree should be written before the build.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Where the built docs portal HTML should be rendered.",
    )
    parser.add_argument(
        "--openapi-url",
        default=docs_site.OPENAPI_DEFAULT_URL,
        help="Optional OpenAPI schema URL to snapshot during docs generation. Use an empty string to force the fallback snapshot.",
    )
    parser.add_argument(
        "--pagefind-root-selector",
        default="article",
        help="CSS selector that bounds the HTML content Pagefind should index.",
    )
    args = parser.parse_args(argv)

    try:
        build_docs_portal(
            generated_dir=Path(args.generated_dir).resolve(),
            output_dir=Path(args.output_dir).resolve(),
            openapi_url=args.openapi_url or None,
            pagefind_root_selector=args.pagefind_root_selector,
        )
        print(f"Built docs portal with Pagefind: {args.output_dir}")
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        return emit_cli_error("Docs portal build", exc)


if __name__ == "__main__":
    raise SystemExit(main())
