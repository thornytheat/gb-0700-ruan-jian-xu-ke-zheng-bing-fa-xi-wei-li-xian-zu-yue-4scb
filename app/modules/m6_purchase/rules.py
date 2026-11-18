from decimal import Decimal
from app.report import report

def seat_hours(rows):
    return sum((r["b"]-r["a"])*r["excess"]/Decimal(3600) for r in rows)

def apply(ctx):
    """采购对照按当前视图分组：合并池一行，旧版分产品视图按原契约逐行。

    超用归属同时保留池汇总与原产品契约明细，两边相加一致。
    """
    out=[]
    groups={}
    for r in ctx["usage"]:
        groups.setdefault((r["pool"],r["view"],r["product"]),[]).append(r)
    for (pool,view,product),rows in sorted(groups.items()):
        credit={}
        for segment in rows:
            for item in segment["offenders"]:
                credit[item["contract"]]=credit.get(item["contract"],0)+item["seats"]*(segment["b"]-segment["a"])/Decimal(3600)
        out.append({"pool":pool,"product":product,"view":view,
                    "contract":product if view=="legacy" else "",
                    "peak":max(r["concurrent"] for r in rows),
                    "capacity":max(r["capacity"] for r in rows),
                    "excess_seat_hours":seat_hours(rows),
                    "overuse_segments":sum(r["excess"]>0 for r in rows),
                    "attribution":[{"contract":c,"excess_seat_hours":v} for c,v in sorted(credit.items())]})
    pending=ctx.get("pending_leases") or []
    ctx["purchase"]=out
    if pending:
        # 切换未完成时，以合并产品签发的新租约没有独立的原采购，旧版分产品视图
        # 无法单独限席。单列一行"待切换"，席位照实呈现，不并入任何原产品。
        from app.modules.m4_concurrency.rules import sweep
        ctx["purchase"].append({"pool":pending[0]["pool"],"product":pending[0]["pool"],"view":"pending",
                               "contract":"","peak":max((x["count"] for x in sweep(pending)),default=0),
                               "capacity":0,"excess_seat_hours":Decimal(0),"overuse_segments":0,
                               "pending_leases":len(pending),
                               "pending_seats":sum(x["quantity"] for x in pending),
                               "attribution":[]})
        out=ctx["purchase"]
    ctx["balance"]={"input":ctx["input_count"],"accepted":ctx["input_count"]-len(ctx["quarantine"])-ctx["blank_rows"],"quarantined":len(ctx["quarantine"]),"blank":ctx["blank_rows"]}
    return report(ctx["purchase"],席位池=len({r["pool"] for r in out}),产品=len(out),超用席位小时=seat_hours(ctx["usage"]))
