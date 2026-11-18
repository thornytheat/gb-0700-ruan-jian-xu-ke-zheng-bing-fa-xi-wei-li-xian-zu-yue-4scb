from app.report import report,quarantine

def close_time(kind,start,end,releases):
    if kind=="offline":return end
    times=[t for t in releases if start<=t<end]
    return min(times) if times else end

def apply(ctx):
    """裁决租约。

    租约主键是(原产品契约, 租约号)：产品线合并不会改写旧租约身份。释放事件
    只按签发时的原契约匹配；把旧回执改挂到合并产品不会结束任何旧租约，而是
    作为契约不匹配进入审计。
    """
    chosen={};audit=[]
    for r in ctx["normalized"]:
        if r["kind"] not in {"online","offline"}:continue
        key=(r["contract"],r["lease_id"])
        if key not in chosen or r["rev"]>chosen[key]["rev"]:
            if key in chosen:audit.append({"id":chosen[key]["lease_id"],"reason":"SUPERSEDED"})
            chosen[key]=r
        elif r["rev"]==chosen[key]["rev"]:
            quarantine(ctx,r,"LEASE_CONFLICT")
        else:audit.append({"id":r["lease_id"],"reason":"SUPERSEDED"})
    out=[]
    for key,r in chosen.items():
        releases=[x["a"] for x in ctx["normalized"] if x["kind"]=="release" and x["contract"]==key[0] and x["lease_id"]==key[1] and x["rev"]==r["rev"]]
        x=dict(r);x["b"]=close_time(r["kind"],r["a"],r["b"],releases);out.append(x)
        if r["kind"]=="offline" and releases:audit.append({"id":r["lease_id"],"reason":"OFFLINE_UNTIL_EXPIRY"})
    # 释放回执的契约核验：只认签发产品与同版租约。旧租约不会因为合并产品上
    # 的同号回执而释放，也不会把回执改挂到新契约。
    versions={(r["contract"],r["lease_id"],r["rev"]) for r in chosen.values()}
    for r in ctx["normalized"]:
        if r["kind"]!="release":continue
        if (r["contract"],r["lease_id"],r["rev"]) in versions:continue
        same_contract=any(c==r["contract"] and i==r["lease_id"] for c,i,_ in versions)
        other=any(c!=r["contract"] and i==r["lease_id"] for c,i,_ in versions)
        if same_contract:
            audit.append({"id":r["lease_id"],"reason":"RELEASE_VERSION_MISMATCH","contract":r["contract"],"line":r.get("line",0)})
        elif other:
            audit.append({"id":r["lease_id"],"reason":"RELEASE_CONTRACT_MISMATCH","contract":r["contract"],"line":r.get("line",0)})
        else:
            audit.append({"id":r["lease_id"],"reason":"RELEASE_UNMATCHED","contract":r["contract"],"line":r.get("line",0)})
    for r in ctx["normalized"]:
        if r["kind"]=="heartbeat":audit.append({"id":r["lease_id"],"reason":"HEARTBEAT_NO_SEAT"})
    ctx["leases"]=out;ctx["lease_audit"]=audit
    return report(out,在线=sum(r["kind"]=="online" for r in out),离线=sum(r["kind"]=="offline" for r in out),
                  契约=len({r["contract"] for r in out}),席位池=len({r["pool"] for r in out}))
