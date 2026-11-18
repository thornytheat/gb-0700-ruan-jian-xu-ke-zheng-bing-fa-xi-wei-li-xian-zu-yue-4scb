# 接口

`POST /api/run`：{"text":"CSV内容"}。同规则版本、池视图与输入摘要只产生一条批次。

`GET/POST /api/1` 至 `/api/7`：独立样例或自定义文件计算。各模块返回 report、quarantine、balance。

`POST /api/review`：id、整数revision、decision取通过或退回。旧版本409；阻断项不能通过。

`GET /api/export/{id}`：唯一证据CSV。`GET /health`：存活检查。

## 席位池

`GET /api/pools`：合并产品与各自原契约，以及所有池的切换状态。

`GET /api/pools/{pool}`：单个池的状态、迁移台账、视图（merged / legacy）。

`POST /api/pools/{pool}/switch`：{"text":"CSV内容", "interrupt_after":N}。开始或接续切换。
`interrupt_after` 可省略（一次完成），仅用于演练中断。同一合并重试只补未迁移租约；
旧租约集合变化返回 409 `SWITCH_CONFLICT`。

`POST /api/pools/{pool}/reset`：显式放弃切换，回到旧版分产品视图。

错误：结构/数值422，版本冲突409，不存在404，文件过大413。逐行异常进入quarantine。
