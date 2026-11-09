
# TalkFinder Code Review Instructions

Review changes for correctness, reliability, security, and maintainability.

## What to Check

1. **Search:** Ensure hybrid search, filters, and embeddings work correctly. Check for broken or inconsistent retrieval logic.

2. **Scheduling:** Detect overlapping confirmed talks when they conflict for the same attendee or resource. Ensure talks are not silently dropped.

3. **Accessibility:** Preserve accessibility requirements throughout search and scheduling. Never silently ignore a user's accessibility preferences.

4. **API:** Check input validation, Pydantic models, API responses, and error handling. Avoid inconsistent data structures.

5. **Security:** Flag exposed secrets, unsafe handling of user input, and sensitive information in logs. Configuration and credentials must come from environment variables.

6. **Testing:** Logic changes should have relevant tests, especially for edge cases and failure scenarios.

## Review Guidelines

- Flag real bugs, security issues, and broken logic.
- Do not flag cosmetic issues or minor style preferences.
- Do not report speculative problems as confirmed defects.
- Explain each finding with the affected code and its potential impact.
- Suggest a fix when possible.
- Prioritize correctness over the number of findings.
