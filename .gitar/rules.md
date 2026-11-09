# Review rules


Review style: be lenient. Only flag real bugs, security issues, and broken logic. Do not flag style, formatting, import order, line length, or minor naming. Do not block a PR for a typo, a comment, or frontend text.

## Generic rules, for any Python FastAPI app

1. Secrets in code. No API keys, tokens, passwords, or endpoint URLs with credentials in any file. All keys and endpoints come from .env only. .env.example must have placeholders only.
2. No hardcoded config that should come from env. Model names, URLs, ports, and dims that depend on a model must come from env or be measured at runtime, not hardcoded in code.
3. One source of truth for a data shape. Use the Pydantic model in models.py. Do not define a second, different shape for the same data in a router or elsewhere.
4. Broken error handling. Bad input must return a clear 400, a missing dependency must return a clear 503, not a 500 or a crash. A missing optional key must fall back safely, not crash the request.
5. Silent drops. If an item is filtered out, full, or clashing, flag it in the response. Never delete it silently.
6. Missing test for a logic change. If a pure logic file changes, a test in tests/ must cover the changed logic. Do not require a test for a typo, a README change, or a frontend text change.