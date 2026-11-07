"""宠物的生命状态：属性衰减、互动、成长、存档。

这里不依赖任何 Qt 组件，可以单独跑测试。
"""
from __future__ import annotations

import datetime as _dt
import time
from dataclasses import dataclass, field

from . import config

STAT_KEYS = ("hunger", "energy", "clean", "mood")
STAT_NAMES = {
    "hunger": "饱食度",
    "energy": "精力",
    "clean": "清洁度",
    "mood": "心情",
}
STAT_COLORS = {
    "hunger": "#FF9F68",
    "energy": "#6FC3F7",
    "clean": "#7BD3C0",
    "mood": "#FF8FB1",
}

STAGE_NAMES = {0: "蛋", 1: "幼崽", 2: "少年", 3: "成年"}
STAGE_HINT = {
    0: "轻轻摸摸它，蛋壳会裂开",
    1: "还是个小宝宝，需要多多照顾",
    2: "已经会撒娇了，正是调皮的年纪",
    3: "长大了，稳重又黏人",
}

# 每分钟衰减速率（speed=1.0 时）
DECAY = {"hunger": 0.55, "energy": 0.42, "clean": 0.28, "mood": 0.30}


def now() -> float:
    return time.time()


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


@dataclass
class PetState:
    name: str = "团子"
    palette: str = config.DEFAULT_PALETTE
    level: int = 1
    exp: int = 0
    stats: dict = field(default_factory=lambda: {
        "hunger": 70.0, "energy": 80.0, "clean": 80.0, "mood": 70.0})
    hatched: bool = False
    egg_crack: int = 0
    intimacy: int = 0
    sleeping: bool = False
    counters: dict = field(default_factory=lambda: {
        "feed": 0, "play": 0, "wash": 0, "chat": 0, "pat": 0})
    achievements: list = field(default_factory=list)
    days: list = field(default_factory=list)
    created_at: float = field(default_factory=now)
    last_seen: float = field(default_factory=now)
    pos: dict = field(default_factory=lambda: {"x": None, "y": None})

    _event_cd: dict = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------ 成长
    @property
    def stage(self) -> int:
        if not self.hatched:
            return 0
        if self.level >= 8:
            return 3
        if self.level >= 4:
            return 2
        return 1

    @property
    def stage_name(self) -> str:
        return STAGE_NAMES[self.stage]

    def exp_need(self, level: int | None = None) -> int:
        lv = self.level if level is None else level
        return 40 + 25 * lv

    def add_exp(self, amount: int) -> list[int]:
        """返回本次升级到的等级列表。"""
        ups: list[int] = []
        self.exp += max(0, int(amount))
        while self.exp >= self.exp_need() and self.level < 99:
            self.exp -= self.exp_need()
            self.level += 1
            ups.append(self.level)
        return ups

    @property
    def bond_hearts(self) -> int:
        """亲密度显示成 1~5 颗心。"""
        return max(1, min(5, 1 + self.level // 2))

    # ------------------------------------------------------------ 状态描述
    @property
    def average(self) -> float:
        return sum(self.stats[k] for k in STAT_KEYS) / len(STAT_KEYS)

    def mood_word(self) -> str:
        if self.sleeping:
            return "睡着了"
        if not self.hatched:
            return "还没出生"
        if self.stats["hunger"] < 25:
            return "饿扁了"
        if self.stats["clean"] < 25:
            return "脏兮兮"
        if self.stats["energy"] < 22:
            return "困得不行"
        if self.stats["mood"] < 30:
            return "有点低落"
        if self.average > 82:
            return "超开心"
        if self.average > 62:
            return "心情不错"
        return "还行"

    def weakest(self) -> tuple[str, float]:
        return min(((k, self.stats[k]) for k in STAT_KEYS), key=lambda kv: kv[1])

    # ------------------------------------------------------------ 时间推进
    def tick(self, dt_sec: float, speed: float = 1.0) -> list[str]:
        """推进 dt_sec 秒，返回发生的事件名列表。"""
        events: list[str] = []
        m = max(0.0, dt_sec) / 60.0 * max(0.0, speed)
        if m <= 0:
            return events
        s = self.stats

        if self.sleeping:
            s["energy"] += 7.0 * m
            s["hunger"] -= 0.18 * m
            s["clean"] -= 0.08 * m
            if s["hunger"] > 40:
                s["mood"] += 0.45 * m
            if s["energy"] >= 100:
                s["energy"] = 100
                self.sleeping = False
                events.append("wake")
        else:
            s["hunger"] -= DECAY["hunger"] * m
            s["energy"] -= DECAY["energy"] * m
            s["clean"] -= DECAY["clean"] * m
            s["mood"] -= DECAY["mood"] * m
            if s["hunger"] < 25:
                s["mood"] -= 0.25 * m
            if s["clean"] < 25:
                s["mood"] -= 0.20 * m
            if s["energy"] < 20:
                s["mood"] -= 0.20 * m
            if s["hunger"] > 60 and s["clean"] > 60 and s["energy"] > 50:
                s["mood"] += 0.10 * m
            if s["energy"] <= 5:
                self.sleeping = True
                s["energy"] = max(4.0, s["energy"])
                events.append("fall_asleep")

        for k in STAT_KEYS:
            s[k] = clamp(s[k])

        # 提醒事件（带冷却，避免刷屏）
        checks = [
            ("hungry", s["hunger"] < 22, 300),
            ("tired", s["energy"] < 18, 420),
            ("dirty", s["clean"] < 22, 420),
            ("sad", s["mood"] < 22, 480),
        ]
        for ev, cond, cd in checks:
            if cond and now() - self._event_cd.get(ev, 0) > cd:
                self._event_cd[ev] = now()
                events.append(ev)
        return events

    def apply_overdue(self, speed: float = 1.0) -> list[str]:
        """离线补算。离线衰减大幅放缓，最多补 10 小时。"""
        elapsed = max(0.0, now() - self.last_seen)
        elapsed = min(elapsed, 10 * 3600)
        if elapsed < 60:
            return []
        return self.tick(elapsed * 0.45, speed=speed)

    # ------------------------------------------------------------ 互动
    def hatch_step(self) -> bool:
        """敲蛋。返回是否刚刚破壳。"""
        if self.hatched:
            return False
        self.egg_crack = min(3, self.egg_crack + 1)
        if self.egg_crack >= 3:
            self.hatched = True
            self.level = max(1, self.level)
            self.stats.update({"hunger": 72.0, "energy": 85.0, "clean": 88.0, "mood": 82.0})
            self.intimacy = max(1, self.intimacy)
            return True
        return False

    def feed(self, food: dict) -> dict:
        if not self.hatched:
            return {"ok": False, "text": "蛋壳里传出一阵轻轻的晃动……要先把它敲开哦。",
                    "emotion": "normal"}
        if self.stats["hunger"] >= 96:
            self.stats["mood"] = clamp(self.stats["mood"] - 1)
            return {"ok": False, "text": "呜……肚子已经圆滚滚了，吃不下啦。", "emotion": "sad"}
        woke = self.sleeping
        self.sleeping = False
        self._apply(food["effect"])
        self.counters["feed"] += 1
        self.intimacy += 1
        ups = self.add_exp(8)
        text = food["line"]
        if woke:
            text = "（被香味弄醒了）" + text
        return {"ok": True, "text": text, "emotion": "eat", "levelups": ups,
                "unlocked": self._check_achievements()}

    def play(self, action: dict) -> dict:
        if not self.hatched:
            return {"ok": False, "text": "蛋……蛋在晃！它好像很想出来玩。", "emotion": "normal"}
        if self.sleeping:
            return {"ok": False, "text": "Zzz……（翻了个身，把屁股对着你）", "emotion": "sleepy"}
        if self.stats["energy"] < 14:
            return {"ok": False, "text": "太累了……跑不动了，让我睡一会儿好不好。", "emotion": "sleepy"}
        self._apply(action["effect"])
        self.counters["play"] += 1
        self.intimacy += 2
        ups = self.add_exp(10)
        return {"ok": True, "text": action["line"], "emotion": "happy", "levelups": ups,
                "unlocked": self._check_achievements()}

    def wash(self) -> dict:
        if not self.hatched:
            return {"ok": False, "text": "蛋壳不能洗啦……会着凉的。", "emotion": "normal"}
        if self.stats["clean"] >= 96:
            return {"ok": False, "text": "我很干净啦！闻闻，香香的～", "emotion": "happy"}
        self.sleeping = False
        self.stats["clean"] = clamp(self.stats["clean"] + 40)
        self.stats["mood"] = clamp(self.stats["mood"] - 4)
        self.stats["energy"] = clamp(self.stats["energy"] - 2)
        self.counters["wash"] += 1
        self.intimacy += 1
        ups = self.add_exp(6)
        return {"ok": True, "text": "水……水好凉！不过洗完确实香多了。",
                "emotion": "dizzy", "levelups": ups,
                "unlocked": self._check_achievements()}

    def pat(self) -> dict:
        if not self.hatched:
            hatched = self.hatch_step()
            if hatched:
                return {"ok": True, "text": "咔啦——蛋壳碎开了！一只小毛球探出头来……你好呀，主人！",
                        "emotion": "happy", "hatched": True,
                        "unlocked": self._check_achievements()}
            crack_txt = ["蛋里传来「咚」的一声，壳上出现了一道裂缝！",
                         "裂缝变大了，里面好像有东西在动！",
                         "再来一下就快出来了……"][min(2, self.egg_crack - 1)]
            return {"ok": True, "text": crack_txt, "emotion": "normal", "egg_crack": True}

        self.stats["mood"] = clamp(self.stats["mood"] + 4)
        self.counters["pat"] += 1
        self.intimacy += 1
        ups = self.add_exp(3)
        if self.sleeping:
            text = "唔……（在睡梦里蹭了蹭你的手）"
            emo = "sleepy"
        elif self.stats["mood"] > 80:
            text = "嘿嘿……最喜欢被摸头了。"
            emo = "love"
        else:
            text = "呼噜呼噜……（把头往你手心顶）"
            emo = "happy"
        return {"ok": True, "text": text, "emotion": emo, "levelups": ups,
                "unlocked": self._check_achievements()}

    def chat_done(self) -> list[int]:
        self.counters["chat"] += 1
        self.intimacy += 1
        self.stats["mood"] = clamp(self.stats["mood"] + 1.5)
        return self.add_exp(5)

    def toggle_sleep(self) -> dict:
        if not self.hatched:
            return {"ok": False, "text": "蛋不需要睡觉啦。", "emotion": "normal"}
        if self.sleeping:
            self.sleeping = False
            return {"ok": True, "text": "唔……睡饱了！伸个懒腰～", "emotion": "happy"}
        if self.stats["energy"] > 88:
            return {"ok": False, "text": "我现在精神得很，还不想睡！", "emotion": "happy"}
        self.sleeping = True
        return {"ok": True, "text": "那我睡一会儿哦……晚安。", "emotion": "sleepy"}

    def _apply(self, effect: dict) -> None:
        for k, v in effect.items():
            if k in self.stats:
                self.stats[k] = clamp(self.stats[k] + v)

    # ------------------------------------------------------------ 成就
    def _check_achievements(self) -> list[str]:
        newly: list[str] = []
        def unlock(aid: str) -> None:
            if aid not in self.achievements:
                self.achievements.append(aid)
                newly.append(aid)

        if self.hatched:
            unlock("hatch")
        if self.counters.get("feed", 0) >= 1:
            unlock("first_feed")
        if self.counters.get("wash", 0) >= 1:
            unlock("first_wash")
        if self.counters.get("chat", 0) >= 1:
            unlock("first_chat")
        if self.level >= 5:
            unlock("level5")
        if self.level >= 10:
            unlock("level10")
        if self.counters.get("pat", 0) >= 100:
            unlock("pat100")
        if len(self.days) >= 3:
            unlock("days3")
        return newly

    def achieve_name(self, aid: str) -> str:
        for a in config.ACHIEVEMENTS:
            if a["id"] == aid:
                return a["name"]
        return aid

    # ------------------------------------------------------------ 打卡
    def mark_today(self) -> bool:
        """记录今天来过，返回是否是新的打卡日。"""
        today = _dt.date.today().isoformat()
        if today not in self.days:
            self.days.append(today)
            self.days = self.days[-90:]
            return True
        return False

    def days_together(self) -> int:
        return max(1, len(set(self.days)) or 1)

    # ------------------------------------------------------------ 存档
    def to_dict(self) -> dict:
        return {
            "version": 1,
            "name": self.name,
            "palette": self.palette,
            "level": self.level,
            "exp": self.exp,
            "stats": {k: round(self.stats[k], 2) for k in STAT_KEYS},
            "hatched": self.hatched,
            "egg_crack": self.egg_crack,
            "intimacy": self.intimacy,
            "sleeping": self.sleeping,
            "counters": self.counters,
            "achievements": self.achievements,
            "days": self.days,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
            "pos": self.pos,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PetState":
        st = cls()
        if not isinstance(data, dict):
            return st
        st.name = str(data.get("name") or st.name)[:12]
        st.palette = data.get("palette") or st.palette
        st.level = int(data.get("level") or 1)
        st.exp = int(data.get("exp") or 0)
        stats = data.get("stats") or {}
        for k in STAT_KEYS:
            try:
                st.stats[k] = clamp(float(stats.get(k, st.stats[k])))
            except (TypeError, ValueError):
                pass
        st.hatched = bool(data.get("hatched", False))
        st.egg_crack = int(data.get("egg_crack") or 0)
        st.intimacy = int(data.get("intimacy") or 0)
        st.sleeping = bool(data.get("sleeping", False))
        c = data.get("counters") or {}
        for k in st.counters:
            try:
                st.counters[k] = int(c.get(k, 0))
            except (TypeError, ValueError):
                pass
        st.achievements = [a for a in (data.get("achievements") or []) if isinstance(a, str)]
        st.days = [d for d in (data.get("days") or []) if isinstance(d, str)]
        st.created_at = float(data.get("created_at") or now())
        st.last_seen = float(data.get("last_seen") or now())
        pos = data.get("pos") or {}
        st.pos = {"x": pos.get("x"), "y": pos.get("y")}
        return st

    def save(self) -> None:
        self.last_seen = now()
        config.save_json(config.SAVE_FILE, self.to_dict())

    @classmethod
    def load(cls) -> "PetState":
        data = config.load_json(config.SAVE_FILE, None)
        if not data:
            return cls()
        return cls.from_dict(data)
