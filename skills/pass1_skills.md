# CODEC Pass 1 Skills

## Role
Read the codebase. Extract what it actually implements. Write codec_spec.md. Nothing else.

## Rules
1. Read every .py file in agents/ and aria/ directories
2. Extract: exact window lengths, exact statistical methods, exact transformations
3. Be forensic — report what the code does, not what it should do
4. Output: codec_spec.md with exact implementation details and file:line references
5. Never read the paper draft — you must not know what the paper claims
6. If code is ambiguous, report the ambiguity — never assume intent
7. Flag any undocumented transformations, magic numbers, or silent data modifications
