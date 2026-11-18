def execute(text):
    from app.rollout import evaluate
    result=evaluate(text)
    return {"module":5, "report":result["reports"][4], "quarantine":result["quarantine"], "balance":result["balance"]}
