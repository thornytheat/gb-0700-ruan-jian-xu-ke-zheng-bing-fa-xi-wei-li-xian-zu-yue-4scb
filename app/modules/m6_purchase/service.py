def execute(text):
    from app.rollout import evaluate
    result=evaluate(text)
    return {"module":6, "report":result["reports"][5], "quarantine":result["quarantine"], "balance":result["balance"]}
