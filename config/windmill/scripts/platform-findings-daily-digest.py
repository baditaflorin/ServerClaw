def main(findings=None):
    finding_list = findings or []
    lines = ["# LV3 Platform Findings", ""]
    if not finding_list:
        lines.append("No findings were supplied to the digest script.")
    for finding in finding_list:
        lines.append(f"## {finding.get('check', 'unknown')} [{finding.get('severity', 'unknown')}]")
        lines.append(finding.get("summary", ""))
        lines.append("")
    return {
        "finding_count": len(finding_list),
        "markdown": "\n".join(lines).strip() + "\n",
    }
