def execute(text):
    from app.rollout import evaluate
    result=evaluate(text)
    return {"module":4, "report":result["reports"][3], "quarantine":result["quarantine"], "balance":result["balance"]}
