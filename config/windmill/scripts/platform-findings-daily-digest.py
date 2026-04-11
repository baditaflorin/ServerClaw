def main(findings=None):
    finding_list = findings or []
    lines = ["# LV3 Platform Findings", ""]
    if not finding_list:
        lines.append("No findings were supplied to the digest script.")
    for finding in finding_list:
        lines.append(f"## {finding.get('check', 'unknown')} [{finding.get('severity', 'unknown')}]")
        lines.append(finding.get("summary", ""))
        lines.append("")
    markdown = "\n".join(lines).strip() + "\n"
    _publish_to_outline(markdown)
    return {
        "finding_count": len(finding_list),
        "markdown": markdown,
    }


def _publish_to_outline(markdown: str) -> None:
    import os, subprocess, sys, datetime
    from pathlib import Path

    token = os.environ.get("OUTLINE_API_TOKEN", "")
    if not token:
        for candidate in ["/srv/platform_server", str(Path(__file__).resolve().parents[3])]:
            p = Path(candidate) / ".local" / "outline" / "api-token.txt"
            if p.exists():
                token = p.read_text(encoding="utf-8").strip()
                break
    if not token:
        return
    for candidate in ["/srv/platform_server", str(Path(__file__).resolve().parents[3])]:
        outline_tool = Path(candidate) / "scripts" / "outline_tool.py"
        if outline_tool.exists():
            break
    else:
        return
    date = datetime.date.today().isoformat()
    title = f"findings-digest-{date}"
    try:
        subprocess.run(
            [
                sys.executable,
                str(outline_tool),
                "document.publish",
                "--collection",
                "Platform Findings",
                "--title",
                title,
                "--stdin",
            ],
            input=markdown,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "OUTLINE_API_TOKEN": token},
        )
    except OSError:
        pass
