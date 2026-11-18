def execute(text):
    from app.rollout import evaluate
    result=evaluate(text)
    return {"module":2, "report":result["reports"][1], "quarantine":result["quarantine"], "balance":result["balance"]}
