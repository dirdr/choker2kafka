def tool_summary(name: str, result: dict) -> str:
    if name == "find_prior_incidents":
        return "Reviewed incident memory is unavailable; no historical case supports this finding."
    documents = result.get("documents", [])
    if name == "lookup_producer_context":
        revisions = [
            str(item["data"]["revision"])
            for item in documents
            if item["evidence_id"].startswith("configuration:")
        ]
        missing = result.get("missing_configuration_revisions", [])
        return f"Read {len(revisions)} captured configuration revisions ({', '.join(revisions[-5:]) or 'none'}). {len(missing)} required revisions are missing."
    evaluations = [
        item["data"]
        for item in documents
        if item["evidence_id"].startswith("snapshot:")
    ]
    evaluation = evaluations[0] if evaluations else {}
    metrics = evaluation.get("metrics", {})
    ratio = metrics.get("failure_ratio")
    failure = (
        f"{ratio * 100:.1f}% of the recent window violates the contract."
        if isinstance(ratio, (int, float))
        else "The captured evaluation is available for inspection."
    )
    return f"{failure} Read the contract and a bounded event sample from the frozen incident."
