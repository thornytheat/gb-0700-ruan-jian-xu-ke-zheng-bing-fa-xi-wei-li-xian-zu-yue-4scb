import csv,io,json

def _row(writer,run,kind,line,reason,evidence):
    writer.writerow([run["id"],run["digest"],run["rule_version"],kind,line,reason,json.dumps(evidence,ensure_ascii=False,sort_keys=True)])

def evidence_csv(run):
    out=io.StringIO();writer=csv.writer(out)
    writer.writerow(["run_id","sha256","rule_version","kind","line","reason","evidence"])
    result=run["result"]
    _row(writer,run,"manifest","","",{"balance":result.get("balance"),"decision":run["decision"],"revision":run["revision"],"pool_token":result.get("pool_token","")})
    # 原产品凭据：每份租约一行，契约身份与所在共享池并列。
    for lease in result.get("leases",[]):
        _row(writer,run,"lease",lease.get("line",""),"",{
            "contract":lease.get("contract"),"pool":lease.get("pool"),"lease_id":lease.get("lease_id"),
            "user":lease.get("user"),"kind":lease.get("kind"),"version":lease.get("rev"),
            "seats":lease.get("quantity"),"start":str(lease.get("a")),"end":str(lease.get("b"))})
    # 池切换记录：只列已迁移旧租约；未迁移数量见 pool-switch 行。
    for state in result.get("pool_switches",[]):
        _row(writer,run,"pool-switch","","",{
            "pool":state.get("pool"),"status":state.get("status"),"attempt":state.get("attempt"),
            "view":state.get("view"),"migrated":state.get("migrated"),"remaining":state.get("remaining"),
            "seats":state.get("seats"),"migrated_seats":state.get("migrated_seats")})
        for item in state.get("migrations",[]):
            _row(writer,run,"pool-migration","","",{
                "pool":state.get("pool"),"contract":item.get("contract"),"lease_id":item.get("lease_id"),
                "version":item.get("lease_version"),"start":item.get("start_at"),"seats":item.get("quantity")})
    # 共享池容量与超用归属：并发、容量、超用、逐契约容量和逐契约责任同段呈现。
    for segment in result.get("usage",[]):
        _row(writer,run,"pool-segment","",segment.get("status"),{
            "pool":segment.get("pool"),"view":segment.get("view"),"product":segment.get("product"),
            "start":str(segment.get("a")),"end":str(segment.get("b")),
            "concurrent":segment.get("concurrent"),"capacity":segment.get("capacity"),
            "excess":segment.get("excess"),
            "capacity_by_contract":segment.get("capacity_by_contract"),
            "contracts":segment.get("contracts"),"offenders":segment.get("offenders")})
    for pool in result.get("purchase",[]):
        _row(writer,run,"pool-attribution","","",pool)
    for row in result.get("quarantine",[]):
        _row(writer,run,"quarantine",row.get("line",""),row["reason"],row)
    for row in result.get("release_audit",[]):
        _row(writer,run,"release-check",row.get("line",""),row["status"],row)
    for row in result.get("final",[]):
        _row(writer,run,"result",row.get("line",""),row.get("status",""),row)
    return "﻿"+out.getvalue()
