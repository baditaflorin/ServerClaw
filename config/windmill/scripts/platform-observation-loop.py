import os


def main(findings=None, source: str = "controller-observation-loop"):
    finding_list = findings or []
    non_ok = [item for item in finding_list if item.get("severity") != "ok"]
    return {
        "source": source,
        "workspace": os.getenv("WM_WORKSPACE"),
        "job_id_present": bool(os.getenv("WM_JOB_ID")),
        "finding_count": len(finding_list),
        "non_ok_count": len(non_ok),
        "status": "pending-controller-input" if not finding_list else "summarized",
    }
