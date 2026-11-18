"""席位池定义。

产品线合并后，多个原有采购产品共用一个席位池。每份租约的原始产品
凭据（contract）始终保留，池只负责统一限席；释放事件仍按签发产品匹配。
"""

# 合并产品（新租约按此签发） -> 原产品契约（采购与旧回执仍按这些编号）
MERGED_PRODUCTS = {"CAD+RENDER": ("CAD", "RENDER")}

# 合并产品在录入时的可接受写法。原产品别名仍在 m2 中维护。
MERGED_ALIASES = {
    "CAD+RENDER": "CAD+RENDER",
    "CAD_RENDER": "CAD+RENDER",
    "CAD-RENDER": "CAD+RENDER",
    "CAD/RENDER": "CAD+RENDER",
    "CAD&RENDER": "CAD+RENDER",
    "CAD RENDER": "CAD+RENDER",
    "CADRENDER": "CAD+RENDER",
}


def normalize_pool(value):
    """把录入或路径中的池名归一；不认识返回 None。"""
    text = str(value).strip()
    if text in MERGED_ALIASES:
        return MERGED_ALIASES[text]
    return MERGED_ALIASES.get(text.upper())


def pool_for(product):
    """返回产品所属的合并池；非池成员返回 None。"""
    if product in MERGED_PRODUCTS:
        return product
    for pool, members in MERGED_PRODUCTS.items():
        if product in members:
            return pool
    return None


def pool_members(pool):
    return MERGED_PRODUCTS.get(pool, ())


def is_pool_member(pool, product):
    return product in pool_members(pool)


def contracts_for(pool):
    """池的原始契约；单产品池返回自身。"""
    return pool_members(pool) or (pool,)
