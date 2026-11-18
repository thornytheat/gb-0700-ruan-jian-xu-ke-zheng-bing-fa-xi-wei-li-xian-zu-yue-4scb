from app.report import report
from app.pools import MERGED_PRODUCTS, pool_members

def segment_breakdown(active):
    counts={}
    for r in active:
        counts[r["contract"]]=counts.get(r["contract"],0)+r["quantity"]
    return [{"contract":c,"seats":n} for c,n in sorted(counts.items())]

def sweep(leases):
    points=sorted({r[k] for r in leases for k in ("a","b")});out=[]
    for a,b in zip(points,points[1:]):
        active=[r for r in leases if r["a"]<=a<r["b"]]
        if active:out.append({"a":a,"b":b,"count":sum(r["quantity"] for r in active),"ids":sorted(r["lease_id"] for r in active)})
    return out

def _segments(leases,pool,label,view):
    out=[]
    for seg in sweep(leases):
        active=[r for r in leases if r["a"]<=seg["a"]<r["b"]]
        out.append(dict(seg,pool=pool,product=label,view=view,
                        contract=label if view=="legacy" else "",
                        contracts=segment_breakdown(active)))
    return out

def pool_segments(leases):
    """合并池视图：同一池内所有契约租约一起限席，但逐份保留原产品契约。"""
    out=[]
    for pool in sorted({r["pool"] for r in leases}):
        out.extend(_segments([r for r in leases if r["pool"]==pool],pool,pool,"merged"))
    return out

def legacy_segments(leases):
    """旧版分产品视图：只按签发时的原产品契约分别限席。

    以合并产品签发的新租约没有独立的原采购，无法在分产品视图里单独限席
    （否则会把共享池容量重复算进每个原产品）。它们在切换完成前只作为
    "待切换新租约"登记，不进入旧版限席，避免虚增并发或虚增超用。
    """
    out=[]
    for contract in sorted({r["contract"] for r in leases}):
        if contract in MERGED_PRODUCTS:continue
        rows=[r for r in leases if r["contract"]==contract]
        out.extend(_segments(rows,rows[0]["pool"],contract,"legacy"))
    return out

def view_mode(pool,views):
    """合并池默认统一限席；只有切换未完成时落回旧版分产品视图。
    单产品池没有共享语义，始终保持分产品视图。"""
    if len(pool_members(pool))<=1:return "legacy"
    return "legacy" if (views or {}).get(pool)=="legacy" else "merged"

def apply(ctx):
    views=ctx.get("pool_views") or {}
    merged=pool_segments(ctx["leases"]);legacy=legacy_segments(ctx["leases"])
    out=[]
    for pool in sorted({r["pool"] for r in ctx["leases"]}):
        source=merged if view_mode(pool,views)=="merged" else legacy
        out.extend(r for r in source if r["pool"]==pool)
    out.sort(key=lambda r:(r["pool"],r["a"],r["product"]))
    ctx["segments"]=out;ctx["segments_merged"]=merged;ctx["segments_legacy"]=legacy
    pending=[r for r in ctx["leases"] if view_mode(r["pool"],views)=="legacy" and r["contract"] in MERGED_PRODUCTS]
    ctx["pending_leases"]=pending
    return report(out,峰值=max((r["count"] for r in out),default=0),区间=len(out),
                  席位池=len({r["pool"] for r in out}),
                  合并池视图=sum(r["view"]=="merged" for r in out),
                  分产品视图=sum(r["view"]=="legacy" for r in out),
                  待切换新租约=len(pending))
