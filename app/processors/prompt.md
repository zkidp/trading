# DeepSeek prompt (notes)

We require **STRICT JSON array** output, length must equal the input titles length.

Each element:
- ticker: string (e.g. "AAPL") or null
- sentiment: float in [-1,1]
- summary: <= 30 Chinese chars
- risk_tags: array of strings

If ticker is unclear => null (no guessing).
