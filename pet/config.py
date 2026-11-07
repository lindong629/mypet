"""全局配置：路径、配色、食物、成就、默认设置。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "桌面宠物"
APP_ID = "DesktopPet"
APP_VERSION = "1.0.0"


# ---------------------------------------------------------------- 数据目录
def data_dir() -> Path:
    """Windows 用 %APPDATA%\\DesktopPet，其他平台用 ~/.local/share/DesktopPet。"""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
    d = base / APP_ID
    d.mkdir(parents=True, exist_ok=True)
    return d


SAVE_FILE = data_dir() / "save.json"
SETTINGS_FILE = data_dir() / "settings.json"


# ---------------------------------------------------------------- 配色方案
# 按真实猫的毛色配置：
#   fur 主体毛色 / fur_dark 暗部·条纹 / fur_light 胸腹口鼻的浅色毛
#   ear 耳内 / nose 鼻镜 / eye 虹膜 / accent 界面强调色
#   pattern: tabby 虎斑 / tuxedo 奶牛 / point 重点色 / solid 纯色
# body/dark/belly/blush 是旧字段，保留给界面模块用
PALETTES = {
    "橘白猫": {
        "fur": "#E1A463", "fur_dark": "#B1713A", "fur_light": "#FFF3E2",
        "ear": "#E8A9A2", "nose": "#D98F8B", "eye": "#8FA84C",
        "accent": "#E08A45", "pattern": "tabby",
    },
    "狸花猫": {
        "fur": "#A9875F", "fur_dark": "#6A5136", "fur_light": "#EBDCC3",
        "ear": "#DCA79E", "nose": "#C98580", "eye": "#8A9F48",
        "accent": "#A9793F", "pattern": "tabby",
    },
    "蓝灰英短": {
        "fur": "#A9B2BE", "fur_dark": "#7A8493", "fur_light": "#EEF1F5",
        "ear": "#D8A9AB", "nose": "#BE8D90", "eye": "#E5A84B",
        "accent": "#7E90A8", "pattern": "solid",
    },
    "奶牛猫": {
        "fur": "#565052", "fur_dark": "#2B2729", "fur_light": "#F8F3E9",
        "ear": "#C99795", "nose": "#3C3235", "eye": "#B7CE72",
        "accent": "#6E7684", "pattern": "tuxedo",
    },
    "布偶猫": {
        "fur": "#F0E6D8", "fur_dark": "#A98C74", "fur_light": "#FFFCF6",
        "ear": "#E0B4AF", "nose": "#DFA9A6", "eye": "#6FA9DE",
        "accent": "#C9A98B", "pattern": "point",
    },
}

# 旧存档里的配色名做个映射，免得升级后变回默认
PALETTE_ALIAS = {
    "奶油橘": "橘白猫",
    "薄荷奶绿": "蓝灰英短",
    "樱粉团子": "布偶猫",
    "夜空灰蓝": "奶牛猫",
}

DEFAULT_PALETTE = "橘白猫"

# 补齐旧字段，界面里用 palette["body"] 之类的地方不用改
for _name, _p in PALETTES.items():
    _p.setdefault("body", _p["fur"])
    _p.setdefault("dark", _p["fur_dark"])
    _p.setdefault("belly", _p["fur_light"])
    _p.setdefault("blush", "#F09B9B")
    _p.setdefault("pattern", "tabby")

# ---------------------------------------------------------------- 食物
# effect 中的键与 PetState.stats 对应；clean 为负表示会弄脏
FOODS = [
    {
        "id": "fish", "color": "#E8A15C", "name": "小鱼干", "icon": "fish",
        "desc": "香脆可口，是团子的最爱",
        "effect": {"hunger": 16, "mood": 5, "clean": -2},
        "line": "小鱼干！咔嚓咔嚓～最喜欢了！",
    },
    {
        "id": "milk", "color": "#F3EFE4", "name": "温牛奶", "icon": "milk",
        "desc": "暖暖的，喝完会有点困",
        "effect": {"hunger": 8, "energy": 8, "mood": 2},
        "line": "咕嘟咕嘟……好暖和，想睡觉了。",
    },
    {
        "id": "cake", "color": "#F0BFC8", "name": "草莓蛋糕", "icon": "cake",
        "desc": "甜食让人开心，但会弄脏胡子",
        "effect": {"hunger": 12, "mood": 12, "clean": -6, "energy": -2},
        "line": "甜甜的！嘴角沾到奶油了……嘿嘿。",
    },
    {
        "id": "apple", "color": "#D9694F", "name": "脆苹果", "icon": "apple",
        "desc": "清脆健康，吃完清清爽爽",
        "effect": {"hunger": 10, "clean": 2, "mood": 3},
        "line": "咔嚓！好清脆，牙齿都变干净了。",
    },
    {
        "id": "pudding", "color": "#E5C378", "name": "焦糖布丁", "icon": "pudding",
        "desc": "滑滑嫩嫩，心情变好",
        "effect": {"hunger": 9, "mood": 9},
        "line": "软软的……像云朵一样，好幸福。",
    },
]

FOOD_BY_ID = {f["id"]: f for f in FOODS}

# ---------------------------------------------------------------- 玩耍
PLAY_ACTIONS = [
    {
        "id": "yarn", "name": "玩毛线球",
        "effect": {"energy": -9, "mood": 12, "hunger": -5, "clean": -3},
        "line": "毛线球滚呀滚……抓到啦！再来一次！",
    },
    {
        "id": "wand", "name": "逗猫棒",
        "effect": {"energy": -12, "mood": 15, "hunger": -6},
        "line": "那个羽毛！我一定要抓住它！嘿！嘿！",
    },
    {
        "id": "hide", "name": "捉迷藏",
        "effect": {"energy": -7, "mood": 10, "clean": -4},
        "line": "躲好了吗？那我来找你咯……找到你啦！",
    },
]

# ---------------------------------------------------------------- 成就
ACHIEVEMENTS = [
    {"id": "hatch", "name": "破壳而出", "desc": "把蛋敲开，认识你的新朋友"},
    {"id": "first_feed", "name": "第一次投喂", "desc": "喂它吃点东西"},
    {"id": "first_wash", "name": "洗香香", "desc": "给它洗一次澡"},
    {"id": "first_chat", "name": "第一次对话", "desc": "和它聊上几句"},
    {"id": "level5", "name": "亲密伙伴", "desc": "把它养到 5 级"},
    {"id": "level10", "name": "长大成人", "desc": "把它养到 10 级"},
    {"id": "pat100", "name": "摸头狂魔", "desc": "累计抚摸 100 次"},
    {"id": "days3", "name": "陪伴三天", "desc": "连续陪伴 3 天"},
]

# ---------------------------------------------------------------- 大模型服务商预设
# keyless=True 表示不用密钥也能用；base_url 都验证过是真实存在的 OpenAI 兼容接口
LLM_PRESETS = [
    {
        "id": "zhipu",
        "name": "智谱 GLM（首选 · 国内直连 · 免费）",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4.7-flash",
        "keyless": False,
        "signup": "https://open.bigmodel.cn/usercenter/apikeys",
        "note": "免费的是 glm-4.7-flash 和 glm-4-flash（输入输出都 0 元），需实名认证。"
                "本程序会自动让 glm-4.7-flash 关闭思考，实测 1 秒内回复；"
                "高峰偶尔会排队，这时自动退回本地词库。glm-5.x 系列是付费的"
                "（输入 0.8 / 输出 2.8 元每百万 token），别用它们闲聊。",
    },
    {
        "id": "modelscope",
        "name": "魔搭 ModelScope（每天约 2000 次免费）",
        "base_url": "https://api-inference.modelscope.cn/v1",
        "model": "ZhipuAI/GLM-4.7-Flash",
        "keyless": False,
        "signup": "https://modelscope.cn/my/myaccesstoken",
        "note": "阿里旗下，每人每天约 2000 次免费调用（以官方为准），够聊很久。"
                "需绑定阿里云账号并实名，然后在「我的 Token」页复制 Access Token 当密钥用。",
    },
    {
        "id": "pollinations",
        "name": "免注册试用（每 45 秒只能回一条）",
        "base_url": "https://text.pollinations.ai/openai",
        "model": "openai",
        "keyless": True,
        "signup": "",
        "note": "不用注册、不用密钥，勾上就能试。但匿名额度限制很严：每 45 秒只能回一条，"
                "国内也可能连不上。只适合先看看效果，长期用请换智谱。",
    },
    {
        "id": "siliconflow",
        "name": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "keyless": False,
        "signup": "https://cloud.siliconflow.cn/account/ak",
        "note": "注册送额度，部分小参数模型长期免费；模型名建议点「刷新模型」选。",
    },
    {
        "id": "dashscope",
        "name": "阿里通义百炼",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "keyless": False,
        "signup": "https://bailian.console.aliyun.com/",
        "note": "新用户有免费额度，之后按量付费，价格很低。",
    },
    {
        "id": "ollama",
        "name": "本地 Ollama（不联网 · 不限量 · 完全免费）",
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5:3b",
        "keyless": True,
        "signup": "https://ollama.com/download",
        "note": "不用密钥、不联网、不限量。需要先装 Ollama，再执行 ollama pull qwen2.5:3b（约 2GB）。",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek（很便宜 · 没有免费额度）",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "keyless": False,
        "signup": "https://platform.deepseek.com/api_keys",
        "note": "按量付费，聊一次不到一分钱，但确实没有免费额度。",
    },
    {
        "id": "custom",
        "name": "自定义",
        "base_url": "",
        "model": "",
        "keyless": False,
        "signup": "",
        "note": "任何兼容 OpenAI /chat/completions 的接口都能接。",
    },
]


def preset_by_id(pid: str) -> dict:
    for p in LLM_PRESETS:
        if p["id"] == pid:
            return p
    return {}


def preset_by_base_url(base_url: str) -> dict:
    base = (base_url or "").rstrip("/")
    for p in LLM_PRESETS:
        if p["base_url"] and p["base_url"].rstrip("/") == base:
            return p
    return {}


# ---------------------------------------------------------------- 默认值
DEFAULT_SETTINGS = {
    "pet_name": "团子",
    "palette": DEFAULT_PALETTE,
    "scale": 1.0,
    "always_on_top": True,
    "allow_wander": True,
    "decay_speed": 1.0,
    "owner_name": "主人",
    "autostart": False,
    "llm": {
        "enabled": False,
        "provider": "zhipu",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key": "",
        "model": "glm-4.7-flash",
    },
}

DECAY_PRESETS = {"轻松": 0.5, "正常": 1.0, "严格": 1.6}


# ---------------------------------------------------------------- 读写工具
def load_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_settings() -> dict:
    data = load_json(SETTINGS_FILE, {})
    merged = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        llm = dict(DEFAULT_SETTINGS["llm"])
        llm.update(data.get("llm") or {})
        merged.update({k: v for k, v in data.items() if k != "llm"})
        merged["llm"] = llm
    return merged


def save_settings(settings: dict) -> None:
    save_json(SETTINGS_FILE, settings)


def palette_of(settings: dict) -> dict:
    name = settings.get("palette", DEFAULT_PALETTE)
    name = PALETTE_ALIAS.get(name, name)
    return PALETTES.get(name, PALETTES[DEFAULT_PALETTE])


def app_font_family() -> list[str]:
    if sys.platform.startswith("win"):
        return ["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"]
    if sys.platform == "darwin":
        return ["PingFang SC", "Hiragino Sans GB", "Helvetica Neue"]
    return ["Noto Sans CJK SC", "WenQuanYi Micro Hei", "Sans Serif"]
