from fastapi import FastAPI, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.errors import BusinessError, object_payload
from app.pipeline import sample_text
from app.rollout import evaluate, save_run, start_or_resume, current
from app.pools import MERGED_PRODUCTS, normalize_pool, pool_members
from app import store
from app.exporter import evidence_csv
from app.timeops import display_full
from app.numbers import display_number
from pathlib import Path
import importlib

def brief(value):
    """表格里把契约明细/责任分配压成一行可读文本。"""
    if isinstance(value,dict):
        return " ".join(f"{k}={brief(v)}" for k,v in value.items())
    if isinstance(value,(list,tuple)):
        return " · ".join(brief(v) for v in value)
    return "" if value is None else str(value)

app=FastAPI(title='软件许可证并发席位与离线租约')
app.mount("/static",StaticFiles(directory=Path(__file__).parent/"static"),name="static")
templates=Jinja2Templates(directory=Path(__file__).parent/"templates")
templates.env.filters["utc_instant"]=display_full
templates.env.filters["display_number"]=display_number
templates.env.filters["brief"]=brief
MODULES=['会话接收', '产品映射', '租约裁决', '并发扫描', '超用归属', '采购对照', '补传审计']
for n,slug in enumerate(['sessions', 'products', 'leases', 'concurrency', 'excess', 'purchase', 'audit'],1):
    app.include_router(importlib.import_module(f"app.modules.m{n}_{slug}.handler").router)
@app.exception_handler(BusinessError)
async def domain_error(request,exc):
    return JSONResponse({"error":exc.code,"message":str(exc)},status_code=exc.status)
@app.get("/health")
def health(): return {"status":"ok"}
@app.get("/",response_class=HTMLResponse)
def home(request:Request): return page(request,1)
@app.get("/module/{module}",response_class=HTMLResponse)
def page(request:Request,module:int):
    if module not in range(1,8): raise BusinessError("MODULE","模块不存在",404)
    ident=request.query_params.get("run_id")
    item=store.get(ident) if ident else save_run(sample_text())
    return templates.TemplateResponse(request=request,name="workbench.html",context={
        "title":'软件许可证并发席位与离线租约',"modules":MODULES,"active":module,"run":item,
        "report":item["result"]["reports"][module-1],
        "pools":MERGED_PRODUCTS,"switches":item["result"].get("pool_switches",[]),
        "pool_view":{s["pool"]:s["view"] for s in item["result"].get("pool_switches",[])}})
@app.post("/api/run")
def calculate(payload:object=Body(default=None)):
    payload=object_payload(payload)
    text=payload.get("text",sample_text())
    if not isinstance(text,str): raise BusinessError("TEXT","输入须为文本")
    return save_run(text)
@app.get("/api/runs")
def list_runs(): return store.history()
@app.get("/api/runs/{ident}")
def run_detail(ident:str): return store.get(ident)
@app.post("/api/review")
def review(payload:object=Body(...)):
    payload=object_payload(payload)
    if not isinstance(payload.get("id"),str) or not isinstance(payload.get("decision"),str): raise BusinessError("REVIEW","复核编号与决定须为文本")
    if type(payload.get("revision")) is not int: raise BusinessError("REVISION","版本须为整数")
    return store.review(str(payload.get("id","")),payload["revision"],payload.get("decision"))
@app.get("/api/export/{ident}")
def export(ident:str):
    return Response(evidence_csv(store.get(ident)),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=evidence.csv"})
@app.get("/api/sample")
def sample(): return {"text":sample_text()}

@app.get("/api/pools")
def pools():
    return {"pools":[{"pool":p,"contracts":list(c)} for p,c in MERGED_PRODUCTS.items()],"switches":store.switch_list()}
@app.get("/api/pools/{pool}")
def pool_state(pool:str):
    name=normalize_pool(pool)
    if not name or len(pool_members(name))<2: raise BusinessError("POOL","该产品不属于可合并席位池",404)
    return current(name)
@app.post("/api/pools/{pool}/switch")
def pool_switch(pool:str,payload:object=Body(default=None)):
    """开始或接续池切换。interrupt_after 仅用于演练中断；重试同一合并只补未迁移项。"""
    payload=object_payload(payload) if payload is not None else {}
    name=normalize_pool(pool)
    if not name or len(pool_members(name))<2: raise BusinessError("POOL","该产品不属于可合并席位池",404)
    text=payload.get("text",sample_text())
    if not isinstance(text,str): raise BusinessError("TEXT","输入须为文本")
    return start_or_resume(text,name,payload.get("interrupt_after"))
@app.post("/api/pools/{pool}/reset")
def pool_reset(pool:str):
    """显式放弃本次切换，回到旧版分产品视图（采购与租约输入不变）。"""
    name=normalize_pool(pool)
    if not name or len(pool_members(name))<2: raise BusinessError("POOL","该产品不属于可合并席位池",404)
    return store.reset_switch(name)
