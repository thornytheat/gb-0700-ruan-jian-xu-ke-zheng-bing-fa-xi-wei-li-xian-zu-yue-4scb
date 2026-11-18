def execute(text):
    from app.rollout import evaluate
    result=evaluate(text)
    return {"module":3, "report":result["reports"][2], "quarantine":result["quarantine"], "balance":result["balance"]}
