"""可选的大模型接入：任何 OpenAI 兼容接口（OpenAI / DeepSeek / 通义 / Ollama 等）。

用标准库 urllib 实现，不引入额外依赖；网络请求放在 QThread 里，避免卡界面。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from PySide6.QtCore import QThread, Signal


class LLMError(Exception):
    pass


# 免费模型之间可以互相顶替：一个在排队就换另一个，反正都不花钱。
FREE_FALLBACK = {
    "glm-4.7-flash": "glm-4-flash",
    "glm-4-flash": "glm-4.7-flash",
}


def _post(url: str, payload: dict, key: str, timeout: int) -> tuple[str, str]:
    """发一次请求，返回 (正文, 思考内容)。错误统一转成中文。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        # 尽量把服务商自己的中文错误说明取出来
        msg = ""
        try:
            err = json.loads(detail).get("error") or {}
            msg = (err.get("message") or "").strip()
        except Exception:
            pass
        if e.code == 401:
            raise LLMError("密钥无效或未通过实名认证（HTTP 401）") from e
        if e.code == 402:
            raise LLMError("账户余额/免费额度不足（HTTP 402），点「刷新模型」换个免费模型试试") from e
        if e.code == 429:
            if msg:
                raise LLMError(f"{msg}（HTTP 429）。免费模型高峰期容易排队，稍等再试") from e
            raise LLMError("请求太频繁（HTTP 429），稍等再试或换个服务商") from e
        if e.code == 404:
            raise LLMError("接口地址或模型名不对（HTTP 404），试试点「刷新模型」") from e
        if e.code == 400 and msg:
            raise LLMError(f"请求被拒绝：{msg}") from e
        raise LLMError(f"接口返回 {e.code}：{msg or detail or e.reason}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"连不上接口：{e.reason}") from e
    except TimeoutError as e:
        raise LLMError("接口响应超时") from e

    try:
        obj = json.loads(raw)
        message = obj["choices"][0]["message"]
    except Exception as e:
        raise LLMError("返回格式看不懂：" + raw[:160]) from e

    return (message.get("content") or "").strip(), (message.get("reasoning_content") or "").strip()


def _request(cfg: dict, messages: list[dict], timeout: int = 45, _depth: int = 0) -> str:
    base = (cfg.get("base_url") or "").strip().rstrip("/")
    key = (cfg.get("api_key") or "").strip()
    model = (cfg.get("model") or "").strip()
    if not base:
        raise LLMError("没有填写接口地址")
    if not model:
        raise LLMError("没有填写模型名称")

    url = base + "/chat/completions"
    zhipu = "bigmodel.cn" in base

    # 智谱 GLM-4.7-Flash 关掉思考只要 0.7 秒，开着要 20 秒以上——先要求关。
    # 但 GLM-5.x 是「始终思考」的型号，会报 1210，这时再退回开启并给足预算。
    if zhipu:
        plans = [({"thinking": {"type": "disabled"}}, 1200),
                 ({"thinking": {"type": "enabled"}}, 4000)]
    else:
        plans = [({}, 1200), ({}, 3000)]

    last: LLMError | None = None
    for extra, budget in plans:
        for attempt in range(3):
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.95,
                "max_tokens": budget,
                "stream": False,
            }
            payload.update(extra)
            try:
                text, reasoning = _post(url, payload, key, timeout)
            except LLMError as e:
                last = e
                msg = str(e)
                if "429" in msg:
                    if attempt < 2:
                        time.sleep(0.8 + attempt * 0.5)   # 免费模型排队，快速再挤两次
                        continue
                    # 挤不进去就换另一个免费模型顶一下，不花钱、也不用等 30 秒。
                    alt = FREE_FALLBACK.get(model) if zhipu else None
                    if alt and _depth == 0:
                        cfg2 = dict(cfg)
                        cfg2["model"] = alt
                        return _request(cfg2, messages, timeout, _depth=1)
                    # 两个都挤不进去，立刻失败，让界面退回本地词库
                    raise
                if "思考" in msg or "1210" in msg:
                    break                # 型号始终思考，换 enabled 档
                raise                    # 密钥错、地址错之类，直接抛
            if text:
                return text
            # 正文为空（预算被思考吃掉），换更大预算的下一档
            last = LLMError("模型把输出预算都用在思考上了，没留下正文")
            break

    raise last or LLMError("模型返回了空内容")


class LLMWorker(QThread):
    """在后台线程里请求大模型。"""

    ok = Signal(str)
    fail = Signal(str)

    def __init__(self, cfg: dict, messages: list[dict], parent=None):
        super().__init__(parent)
        self._cfg = dict(cfg or {})
        self._messages = messages

    def run(self) -> None:  # noqa: D401
        try:
            text = _request(self._cfg, self._messages)
        except LLMError as e:
            self.fail.emit(str(e))
        except Exception as e:  # 兜底，别让线程崩掉
            self.fail.emit(f"未知错误：{e}")
        else:
            self.ok.emit(text)


class LLMTestWorker(QThread):
    """设置页里的「测试连接」。"""

    ok = Signal(str)
    fail = Signal(str)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = dict(cfg or {})

    def run(self) -> None:
        try:
            text = _request(self._cfg, [
                {"role": "user", "content": "只回复两个字：你好"}
            ], timeout=45)
        except LLMError as e:
            self.fail.emit(str(e))
        except Exception as e:
            self.fail.emit(f"未知错误：{e}")
        else:
            self.ok.emit(text.strip()[:40])


def _get_models(cfg: dict, timeout: int = 20) -> list[str]:
    """请求 {base_url}/models，返回模型 id 列表。"""
    base = (cfg.get("base_url") or "").strip().rstrip("/")
    if not base:
        raise LLMError("没有填写接口地址")
    key = (cfg.get("api_key") or "").strip()

    headers = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    req = urllib.request.Request(base + "/models", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise LLMError(f"接口返回 {e.code}（这个服务商可能不支持自动拉取，手填模型名即可）") from e
    except urllib.error.URLError as e:
        raise LLMError(f"连不上接口：{e.reason}") from e

    try:
        obj = json.loads(raw)
    except Exception as e:
        raise LLMError("返回格式看不懂") from e

    items = obj.get("data") if isinstance(obj, dict) else obj
    ids: list[str] = []
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                mid = it.get("id") or it.get("model") or it.get("name")
            else:
                mid = it
            if isinstance(mid, str) and mid:
                ids.append(mid)
    if not ids:
        raise LLMError("没有读到模型列表，手填模型名即可")
    return sorted(set(ids))


class ModelsWorker(QThread):
    """后台拉取模型列表。"""

    ok = Signal(list)
    fail = Signal(str)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = dict(cfg or {})

    def run(self) -> None:
        try:
            models = _get_models(self._cfg)
        except LLMError as e:
            self.fail.emit(str(e))
        except Exception as e:
            self.fail.emit(f"未知错误：{e}")
        else:
            self.ok.emit(models)
