def execute(text):
    from app.rollout import evaluate
    result=evaluate(text)
    return {"module":1, "report":result["reports"][0], "quarantine":result["quarantine"], "balance":result["balance"]}
