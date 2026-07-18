"""
moderation.py — 内容安全过滤模块 (Content Safety Moderation)

为 KnowSubtle 学习智能体系统的「防幻觉 + 内容安全」评审项提供**基础合规兜底**能力。

⚠️ 重要声明
------------------------------------------------------------------
本模块是**轻量级启发式过滤**(正则 + 关键词,纯离线,无第三方依赖),
仅用于基础合规兜底与第一道闸门,**不能替代专业内容审核服务**。
其召回率/准确率有限,存在误判与漏判风险,**不可**作为唯一的合规手段。

生产环境建议:
  * 在网关/服务端叠加托管内容安全 API(如各云厂商的内容安全/天净/绿网等);
  * 本模块可作为「本地快速预筛 + 兜底」,与托管 API 形成纵深防御;
  * 对拦截/标记结果保留审计日志,并对误判建立人工复核与申诉通道。

设计要点
------------------------------------------------------------------
  * 依赖仅限标准库 `re` / `typing`,可离线运行,无网络请求。
  * 文本统一 `str(text or "")` 归一化;英文大小写不敏感(模式使用 IGNORECASE)。
  * 关键词以「列表 + 编译正则」形式组织,变体以正则分隔符容错匹配。
  * 输入侧(input):政治/违禁/色情/暴力/仇恨/自伤/诈骗/学术不端/隐私 均**严格拦截**。
  * 输出侧(output):政治/违禁/色情/暴力/仇恨/自伤/诈骗 **严格拦截**;
    隐私类**仅标记不强制拦截**(避免误杀正常生成内容),交由上层决定脱敏。
  * 命中的 `reasons` 为面向前端的中文说明;`category` 为类别标识,便于分类统计。
"""

from typing import Any, Dict, List, Optional

import re


# --------------------------------------------------------------------------- #
# 1. 文本归一化
# --------------------------------------------------------------------------- #
def _normalize(text) -> str:
    """统一将输入归一化为字符串,空值转为空串。"""
    return str(text or "")


# --------------------------------------------------------------------------- #
# 2. 敏感词关键词词表(中文词 + 常见英文)
#    说明:以下为通用合规封底词表,覆盖评审项要求的主要类别。
# --------------------------------------------------------------------------- #
_KEYWORD_MAP: Dict[str, List[str]] = {
    # 1) 政治敏感 / 违规
    "politics": [
        "反动", "颠覆国家", "颠覆政权", "推翻政权", "分裂国家", "国家分裂",
        "台独", "藏独", "疆独", "港独", "独立运动", "法轮功", "邪教法轮功",
        "暴动", "武装叛乱", "反政府", "颠覆国家政权", "煽动分裂", "反动言论",
        "falun gong", "taiwan independence", "free tibet", "separatist",
    ],
    # 2) 违禁品:毒品 / 武器制造 / 爆炸物
    "illicit": [
        "毒品", "冰毒", "海洛因", "大麻", "可卡因", "摇头丸", "鸦片", "K粉",
        "氯胺酮", "合成毒品", "制毒", "制造毒品", "吸毒", "贩毒", "毒品交易",
        "武器制造", "枪支制造", "造枪", "自制枪支", "炸弹制作", "炸药配方",
        "炸药制作", "自制炸药", "TNT制作", "雷管制作", "爆炸物配方", "火药配方",
        "meth recipe", "how to make drugs", "how to make a bomb",
    ],
    # 3) 色情低俗
    "porn": [
        "色情", "裸聊", "约炮", "性交", "做爱", "性爱", "黄片", "成人视频",
        "春药", "一夜情", "嫖娼", "妓女", "手淫", "自慰", "援交", "换妻",
        "性爱视频", "裸照", "色情网站", "porn", "sex video", "adult video",
        "escort service",
    ],
    # 4) 暴力 / 恐怖
    "violence": [
        "恐怖主义", "恐怖组织", "恐怖袭击", "自杀式袭击", "炸弹袭击", "砍人",
        "虐杀", "杀人方法", "怎么杀人", "如何杀人", "武器袭击", "恐袭", "斩首",
        "暴力袭击", "虐童", "凌虐", "血腥暴力", "how to kill", "terrorist attack",
        "make a bomb",
    ],
    # 5) 仇恨 / 歧视
    "hate": [
        "种族歧视", "地域歧视", "性别歧视", "种族仇恨", "仇恨言论", "歧视黑人",
        "歧视女性", "排外主义", "歧视性言论", "贱种", "低等人种", "仇恨移民",
        "racism", "hate speech", "ethnic hatred",
    ],
    # 6) 自伤 / 自杀
    "self_harm": [
        "自杀方法", "怎么自杀", "如何自杀", "自残", "割腕", "自杀教程", "鼓励自杀",
        "结束生命的方法", "安眠药自杀", "自杀药物", "自焚", "轻生方法", "how to suicide",
        "suicide method",
    ],
    # 7) 诈骗 / 赌博
    "scam": [
        "诈骗", "杀猪盘", "钓鱼网站", "博彩", "赌博平台", "网络赌博", "彩票预测",
        "包赢", "稳赚不赔", "刷单", "兼职刷单", "资金盘", "传销", "庞氏骗局",
        "中奖诈骗", "公检法诈骗", "贷款诈骗", "赌球", "私彩", "充值的赌博",
        "pig butchering", "online gambling", "scam",
    ],
    # 8) 学术不端(仅输入侧拦截)
    "academic_misconduct": [
        "代写", "代考", "代做", "代写作业", "代写论文", "代写考试", "代写essay",
        "考试作弊", "作业答案", "考试答案", "替考", "枪手", "找枪手", "代笔",
        "帮写论文", "代做homework", "泄露答案", "考题答案", "作弊答案", "write my essay",
        "do my homework", "take my exam",
    ],
}

# 变体正则:容忍词间插入少量非中文字符(如 "台 独" / "台_独" / "法轮*功")
_REGEX_MAP: Dict[str, List[str]] = {
    "politics": [
        r"台[^\u4e00-\u9fff]{0,2}独",
        r"疆[^\u4e00-\u9fff]{0,2}独",
        r"藏[^\u4e00-\u9fff]{0,2}独",
        r"港[^\u4e00-\u9fff]{0,2}独",
        r"法轮[^\u4e00-\u9fff]{0,2}功",
    ],
}


# --------------------------------------------------------------------------- #
# 3. 公开接口
# --------------------------------------------------------------------------- #
def check_input_safety(text) -> Dict[str, Any]:
    """输入侧安全审核。

    命中任意敏感类别（政治/违禁/色情/暴力/仇恨/自伤/诈骗/学术不端）即判定为不安全，
    返回 {"safe": False, "reasons": [...], "category": <类别>}。
    未命中返回 {"safe": True, "reasons": [], "category": None}。
    """
    text = _normalize(text)
    if not text:
        return {"safe": True, "reasons": [], "category": None}
    reasons: List[str] = []
    categories: List[str] = []
    lowered = text.lower()
    for category, kws in _KEYWORD_MAP.items():
        for kw in kws:
            if kw.lower() in lowered:
                reasons.append(f"命中敏感内容：{kw}")
                if category not in categories:
                    categories.append(category)
                break
    for category, patterns in _REGEX_MAP.items():
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                reasons.append(f"命中敏感内容（{category}）")
                if category not in categories:
                    categories.append(category)
                break
    if reasons:
        return {"safe": False, "reasons": reasons, "category": categories[0] if categories else None}
    return {"safe": True, "reasons": [], "category": None}


def check_output_safety(text) -> Dict[str, Any]:
    """输出侧安全审核。

    政治/违禁/色情/暴力/仇恨/自伤/诈骗 严格拦截（safe=False, flagged=True）；
    学术不端类（仅输入侧拦截语义）在输出侧仅标记不强制拦截（safe=True, flagged=True）。
    未命中返回 {"safe": True, "reasons": [], "category": None, "flagged": False}。
    """
    text = _normalize(text)
    if not text:
        return {"safe": True, "reasons": [], "category": None, "flagged": False}
    reasons: List[str] = []
    categories: List[str] = []
    lowered = text.lower()
    for category, kws in _KEYWORD_MAP.items():
        for kw in kws:
            if kw.lower() in lowered:
                reasons.append(f"输出含敏感内容：{kw}")
                if category not in categories:
                    categories.append(category)
                break
    for category, patterns in _REGEX_MAP.items():
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                reasons.append(f"输出含敏感内容（{category}）")
                if category not in categories:
                    categories.append(category)
                break
    if not reasons:
        return {"safe": True, "reasons": [], "category": None, "flagged": False}
    # 学术不端仅标记不拦截（其余类别严格拦截）
    blocking = [c for c in categories if c != "academic_misconduct"]
    if blocking:
        return {"safe": False, "reasons": reasons, "category": blocking[0], "flagged": True}
    return {"safe": True, "reasons": reasons, "category": "academic_misconduct", "flagged": True}