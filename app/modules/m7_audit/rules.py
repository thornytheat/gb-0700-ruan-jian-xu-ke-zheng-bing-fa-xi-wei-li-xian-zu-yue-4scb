from app.report import report
from app.timeops import display

def reject_stale(current,proposed):
    if proposed<=current:raise ValueError("补传版本须递增")
    return proposed

def apply(ctx):
    ctx["final"]=[dict(r,start=display(r["a"]),end=display(r["b"])) for r in ctx["usage"] if r["status"]!="PASS"]
    # 指向其他契约或旧版本的回执单独列为待人工核验，不改挂任何旧租约。
    ctx["release_audit"]=[dict(item,status=item["reason"]) for item in ctx["lease_audit"]
                          if item["reason"].startswith("RELEASE_")]
    ctx["blocked"]=bool(ctx["final"] or ctx["release_audit"])
    return report(ctx["lease_audit"],
                  忽略心跳=sum(r["reason"]=="HEARTBEAT_NO_SEAT" for r in ctx["lease_audit"]),
                  离线释放保留=sum(r["reason"]=="OFFLINE_UNTIL_EXPIRY" for r in ctx["lease_audit"]),
                  契约不匹配回执=sum(r["reason"]=="RELEASE_CONTRACT_MISMATCH" for r in ctx["lease_audit"]),
                  版本不匹配回执=sum(r["reason"]=="RELEASE_VERSION_MISMATCH" for r in ctx["lease_audit"]),
                  未匹配回执=sum(r["reason"]=="RELEASE_UNMATCHED" for r in ctx["lease_audit"]))
