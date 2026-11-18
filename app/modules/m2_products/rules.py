from app.timeops import instant
from app.report import report,quarantine
from app.errors import BusinessError
from app.numbers import number
from app.pools import normalize_pool,pool_for
ALIASES={"CAD-Pro":"CAD","cad":"CAD","CAD":"CAD","Render":"RENDER","RENDER":"RENDER"}
def product(text):
    merged=normalize_pool(text)
    if merged:return merged
    if text not in ALIASES:raise BusinessError("PRODUCT","产品未登记")
    return ALIASES[text]

def seats(text):
    value=number(text)
    if value<=0 or value!=value.to_integral_value():raise BusinessError("SEATS","席位须为正整数")
    return int(value)

def apply(ctx):
    out=[]
    for r in ctx["raw"]:
        try:
            x=dict(r);x["canonical"]=product(r["product"]);x["a"]=instant(r["start"]);x["b"]=instant(r["end"]) if r["end"] else x["a"];x["rev"]=int(r["version"]);x["quantity"]=seats(r["seats"])
            if x["rev"]<1:raise BusinessError("VERSION","版本须为正")
            if r["kind"] not in {"online","offline","heartbeat","release","capacity"}:raise BusinessError("KIND","事件类型无效")
            if r["kind"] in {"online","offline","capacity"} and x["b"]<=x["a"]:raise BusinessError("INTERVAL","租约区间无效")
            # 契约身份：签发时的产品编号，之后无论进入哪个池都不改写。
            # 新合并产品以合并名签发，其契约就是合并名；旧租约保留原编号。
            x["contract"]=x["canonical"];x["pool"]=pool_for(x["contract"]) or x["contract"]
            out.append(x)
        except (BusinessError,ValueError) as e:quarantine(ctx,r,getattr(e,"code","VERSION"))
    ctx["normalized"]=out
    return report(out,产品=len({r["contract"] for r in out}),有效事件=len(out),席位池=len({r["pool"] for r in out}))
