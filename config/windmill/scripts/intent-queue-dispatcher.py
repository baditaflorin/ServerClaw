#!/usr/bin/env python3

from scripts.intent_queue_dispatcher import build_parser, main


if __name__ == "__main__":
    args = build_parser().parse_args()
    result = main(
        repo_root=args.repo_root,
        resource_hints=args.resource_hint,
        workflow_hints=args.workflow_hint,
        max_items=args.max_items,
    )
    import json

    print(json.dumps(result, indent=2, sort_keys=True))
