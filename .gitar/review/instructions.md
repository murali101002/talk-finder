
# TalkFinder - Code Review Instructions

These instructions apply to every pull request in TalkFinder.
Evaluate changed code against these requirements in addition to
standard code review for bugs, security, reliability and maintainability.

## 1. Search correctness

- Elasticsearch hybrid search must preserve the intended combination
  of semantic and keyword relevance.
- Search filters must be applied correctly and must not silently
  discard valid results.
- Missing or malformed search parameters must be handled safely.
- Embedding dimensions and model configuration must remain consistent
  with the configured embedding model.
- Do not introduce changes that break indexing or retrieval of talks.

## 2. Conference scheduling and business logic

- A generated agenda must never contain overlapping confirmed sessions.
- Session conflicts must be detected using the actual session time
  intervals, not just matching start times.
- Every retrieved talk must either be accounted for in the result
  or have a clearly explained exclusion reason.
- Capacity constraints and scheduling conflicts must never cause
  talks to disappear silently.
- Preserve the user's explicit scheduling and filtering preferences.

## 3. Accessibility and inclusivity

- Accessibility requirements and accessibility filters must be
  respected throughout search and scheduling.
- Never silently ignore an accessibility constraint.
- Do not introduce logic that excludes talks or attendees based on
  unsupported assumptions about accessibility needs.
- Missing accessibility metadata must be handled explicitly rather
  than treated as proof that a talk is accessible.

## 4. API and data integrity

- Pydantic models must be the source of truth for API request and
  response structures.
- Avoid duplicate or inconsistent representations of the same data.
- Validate user input before passing it to Elasticsearch or other
  external services.
- Return meaningful HTTP errors for invalid input, unavailable
  dependencies and unexpected failures.
- Missing optional fields must not cause unhandled exceptions.
- Preserve backward compatibility unless an API change is intentional.

## 5. Security and configuration

- Never commit API keys, passwords, authentication tokens or secrets.
- Load environment-specific configuration from environment variables.
- Keep .env.example limited to placeholder values.
- Never expose internal errors, credentials or sensitive configuration
  in API responses or logs.
- Validate and sanitize user-controlled inputs before using them
  in queries or other operations.

## 6. Testing requirements

- Every change to search, ranking, filtering, scheduling or other
  business logic must include relevant tests.
- Include negative and edge-case tests, not only happy paths.
- Test empty results, missing fields, malformed inputs, unavailable
  Elasticsearch connections and conflicting sessions where relevant.
- Do not accept a change that breaks existing tests.
- Tests must validate actual behavior, not merely implementation details.

## Review behavior

- Prioritize correctness, security, reliability and functional bugs.
- Report specific violations with file names, affected code and
  an explanation of the potential impact.
- Distinguish confirmed bugs from suggestions or hypothetical concerns.
- Do not flag formatting, import ordering, minor naming preferences
  or cosmetic changes.
- Do not invent requirements that are not documented here.
- Do not suppress standard security or reliability findings.
- Report a blocking finding for a confirmed violation that can
  cause incorrect search results, invalid schedules, data loss,
  security exposure or broken API behavior.
