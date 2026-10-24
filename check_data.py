#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据完整性自检。

用法：
    python scripts/check_data.py

退出码：0 全部通过；1 有问题（会逐条列出）。
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

FIELDS = ["history", "steps", "motifs", "materials", "safety",
          "ageFit", "mistakes", "phrases", "toParent", "extend", "faq"]

# 面向用户的表述禁忌
BANNED = {
    "芭比": "哈尼卡不称「东方芭比娃娃」，用「立体纸偶」",
    "东北剪纸": "应写作「满族民间剪纸」",
    "麦杆": "应写作「麦秆剪贴」",
    "哈斡尔": "应为「达斡尔」",
    "达翰尔": "应为「达斡尔」",
    "爱辉": "应为「瑷珲」",
}

errors = []
warns = []

NEG = ("不称", "别叫", "不要说", "不宜", "不是", "别说", "说成", "比喻", "误称", "勿称")


def find_banned(text):
    """找出真正该报的禁忌词：排除「不称『东方芭比娃娃』」这类否定语境。"""
    hits = []
    for bad in BANNED:
        for m in re.finditer(re.escape(bad), text):
            i = m.start()
            ctx = text[max(0, i - 10):i]
            if any(n in ctx for n in NEG):
                continue
            hits.append(bad)
            break
    return hits


def load(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        errors.append("缺少文件：data/" + name)
        return None
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    themes = load("themes.json")
    cards = load("kb-card.json")
    plans = load("plans.json")
    if not (themes and cards and plans):
        return report()

    order = themes.get("order", [])
    print("主题数：%d ｜ %s" % (len(order), "、".join(order)))

    # ① 元信息
    for k in order:
        if k not in themes.get("theme_meta", {}):
            errors.append("themes.json 缺少 theme_meta[%s]" % k)
        if k not in themes.get("heritage", {}):
            errors.append("themes.json 缺少 heritage[%s]" % k)
        elif len(themes["heritage"][k]) < 60:
            warns.append("heritage[%s] 偏短（%d 字），可能讲不清来历" % (k, len(themes["heritage"][k])))

    # ② 知识卡：11 字段 + 数量要求
    for k in order:
        c = cards.get(k)
        if not c:
            errors.append("kb-card.json 缺少主题 %s" % k)
            continue
        for f in FIELDS:
            if not c.get(f):
                errors.append("知识卡[%s] 缺少字段 %s" % (k, f))
        if len(c.get("faq", [])) != 5:
            warns.append("知识卡[%s].faq 建议 5 组，当前 %d" % (k, len(c.get("faq", []))))
        if len(c.get("extend", [])) != 5:
            warns.append("知识卡[%s].extend 建议 5 条，当前 %d" % (k, len(c.get("extend", []))))
        if len(c.get("phrases", [])) != 3:
            warns.append("知识卡[%s].phrases 建议 3 句，当前 %d" % (k, len(c.get("phrases", []))))
        tp = c.get("toParent", "")
        if tp and not (50 <= len(tp) <= 120):
            warns.append("知识卡[%s].toParent 长度 %d，建议 60–90 字" % (k, len(tp)))
        # 禁忌表述
        blob = json.dumps(c, ensure_ascii=False)
        for hit in find_banned(blob):
            errors.append("知识卡[%s] 出现禁忌表述「%s」：%s" % (k, hit, BANNED[hit]))

    # ③ 方案：7 主题 × 3 班 × 3 套
    total = 0
    for k in order:
        if k not in plans:
            errors.append("plans.json 缺少主题 %s" % k)
            continue
        for age in ("small", "medium", "big"):
            ps = plans[k].get(age, {})
            if len(ps) < 3:
                errors.append("plans[%s][%s] 只有 %d 套，应为 3 套" % (k, age, len(ps)))
            for pk, p in ps.items():
                total += 1
                for f in ("lesson", "story", "riddle", "decor", "task"):
                    if not p.get(f):
                        errors.append("plans[%s][%s][%s] 缺少 %s" % (k, age, pk, f))
                blob = p.get("lesson", "") + p.get("story", "")
                for hit in find_banned(blob):
                    errors.append("plans[%s][%s][%s] 出现禁忌表述「%s」" % (k, age, pk, hit))
    print("方案总数：%d（应为 63）" % total)
    if total != 63:
        warns.append("方案总数 %d，与 README 写的 63 不一致" % total)

    # ④ 材料规则：有没有哪张卡（材料）没有任何主题能用
    mp = os.path.join(DATA, "materials-rules.js")
    if os.path.exists(mp):
        src = io.open(mp, encoding="utf-8").read()
        m = re.search(r"var NEED\s*=\s*\{(.*?)\n\s*\};", src, re.S)
        if m:
            # 只取每个主题 kw 数组里的值，别把 why 文案一起抓进来
            kws = set()
            for arr in re.findall(r"kw://s*//[(.*?)//]", m.group(1), re.S):
                kws.update(re.findall(r"'([^']+)'", arr))
            m2 = re.search(r"var CATS\s*=\s*\[(.*?)\n\s*\];", src, re.S)
            if m2:
                # 只取 chip 名（分组标题以 emoji 开头、且长度较长，排除掉）
                mats = [x for x in re.findall(r"'([^']+)'", m2.group(1)) if len(x) <= 8 and not x[0].isascii()]
                missing = [x for x in mats if x not in kws and not any(x in k or k in x for k in kws)]
                # NEED 里提到、但选项里没有的材料 = 真的漏了
                ghost = [x for x in kws if x not in mats and not any(x in m or m in x for m in mats)]
                if ghost:
                    warns.append("NEED 里写了但材料选项里没有：%s" % "、".join(sorted(ghost)))
    else:
        warns.append("未找到 data/materials-rules.js，跳过材料检查")

    return report()


def report():
    print()
    if warns:
        print("提示（%d）：" % len(warns))
        for w in warns:
            print("  · " + w)
    if errors:
        print("错误（%d）：" % len(errors))
        for e in errors:
            print("  ✗ " + e)
        print("\n结果：未通过")
        return 1
    print("结果：通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
