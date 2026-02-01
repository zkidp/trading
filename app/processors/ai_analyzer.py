from __future__ import annotations

import json
import re
from dataclasses import dataclass

from loguru import logger
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

_TICKER_RE = re.compile(r"^[A-Z]{1,6}([.-][A-Z]{1,4})?$")


@dataclass(frozen=True)
class AnalyzedItem:
    ticker: str | None
    sentiment: float
    summary: str
    risk_tags: list[str]


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _normalize_ticker(v: object) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str):
        return None
    s = v.strip().upper()
    if not s:
        return None
    if not _TICKER_RE.match(s):
        return None
    return s


def _normalize_risk_tags(v: object) -> list[str]:
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for x in v:
        if isinstance(x, str):
            t = x.strip()
            if t:
                out.append(t)
    return out


def _normalize_sentiment(v: object) -> float:
    try:
        f = float(v)  # type: ignore[arg-type]
    except Exception:
        return 0.0
    return _clamp(f, -1.0, 1.0)


def _normalize_summary(v: object) -> str:
    if not isinstance(v, str):
        return ""
    s = v.strip()
    # Hard cap to keep it short; <=30 Chinese chars requested.
    return s[:60]


class AIAnalyzer:
    def __init__(self, api_key: str, batch_size: int = 15, timeout_s: int = 25) -> None:
        self._api_key = api_key
        self._batch_size = batch_size
        self._timeout_s = timeout_s

        # DeepSeek uses an OpenAI-compatible API surface.
        self._client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=timeout_s)

    def analyze_titles(self, titles: list[str]) -> list[AnalyzedItem]:
        """Analyze titles via DeepSeek.

        Contract:
        - Batch size: 10~20
        - Output MUST be strict JSON array; length == input length
        - If parse/length mismatch: raise (caller should skip batch)
        """
        if not titles:
            return []

        out: list[AnalyzedItem] = []
        for i in range(0, len(titles), self._batch_size):
            batch = titles[i : i + self._batch_size]
            try:
                analyzed = self._analyze_batch(batch)
                out.extend(analyzed)
            except Exception:
                logger.exception("AI 分析批次失败：跳过该批次 | batch_size={}", len(batch))
                # Skip the whole batch per spec.
                continue
        return out

    @retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(4), reraise=True)
    def _analyze_batch(self, titles: list[str]) -> list[AnalyzedItem]:
        prompt = self._build_prompt(titles)

        resp = self._client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是严格输出JSON的金融情绪分析助手。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )

        content = (resp.choices[0].message.content or "").strip()
        parsed = self._parse_json_array(content)

        if len(parsed) != len(titles):
            raise ValueError(f"DeepSeek 输出长度不匹配: got={len(parsed)} expected={len(titles)}")

        out: list[AnalyzedItem] = []
        for obj in parsed:
            if not isinstance(obj, dict):
                obj = {}

            ticker = _normalize_ticker(obj.get("ticker"))
            sentiment = _normalize_sentiment(obj.get("sentiment"))
            summary = _normalize_summary(obj.get("summary"))
            risk_tags = _normalize_risk_tags(obj.get("risk_tags"))

            out.append(AnalyzedItem(ticker=ticker, sentiment=sentiment, summary=summary, risk_tags=risk_tags))

        return out

    def _build_prompt(self, titles: list[str]) -> str:
        items = "\n".join([f"{idx+1}. {t}" for idx, t in enumerate(titles)])
        return (
            "请你对以下美股相关新闻/社媒标题做清洗、ticker提取与情绪打分。\n"
            "要求：只输出严格JSON数组（不要markdown、不要解释、不要代码块）。\n"
            "数组长度必须与输入标题数量一致，顺序一一对应。\n"
            "每个元素的字段：\n"
            "- ticker: 股票代码字符串(如 \"AAPL\") 或 null；不确定则必须为null，禁止猜测\n"
            "- sentiment: 浮点数，范围[-1,1]\n"
            "- summary: 一句话中文摘要(<=30字)\n"
            "- risk_tags: 字符串数组，可为空。示例：财报/诉讼/监管/并购/停牌/做空报告\n"
            "\n标题列表：\n"
            f"{items}\n"
        )

    def _parse_json_array(self, content: str) -> list[object]:
        """Parse strict JSON array.

        DeepSeek must return pure JSON. If it returns extra text, we treat as failure.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"DeepSeek 输出不是可解析 JSON: {e}") from e

        if not isinstance(data, list):
            raise ValueError("DeepSeek 输出不是 JSON 数组")
        return data
