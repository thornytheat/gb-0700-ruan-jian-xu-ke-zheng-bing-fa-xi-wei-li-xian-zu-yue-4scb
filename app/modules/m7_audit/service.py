def execute(text):
    from app.rollout import evaluate
    result=evaluate(text)
    return {"module":7, "report":result["reports"][6], "quarantine":result["quarantine"], "balance":result["balance"]}
