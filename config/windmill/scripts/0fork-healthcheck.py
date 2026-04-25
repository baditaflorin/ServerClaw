import os
import socket


def main(probe: str = "ok"):
    return {
        "probe": probe,
        "hostname": socket.gethostname(),
        "workspace": os.getenv("WM_WORKSPACE"),
        "job_id_present": bool(os.getenv("WM_JOB_ID")),
    }
