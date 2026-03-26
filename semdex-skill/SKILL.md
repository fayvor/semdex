---
name: semdex
description: Use semdex semantic search tools when working in codebases to find relevant files, understand architecture, and discover related code. Trigger this skill automatically when exploring unfamiliar code, searching for specific functionality, looking for related files, understanding how features work, finding examples or patterns, or investigating bugs. Always prefer semantic search over grep/find for conceptual queries. Use this skill proactively whenever you need to understand or navigate a codebase.
---

# Using Semdex for Codebase Exploration

Semdex provides semantic search capabilities that understand code meaning, not just keywords. Use these tools proactively to navigate and understand codebases efficiently.

## Available Tools

### 1. `search` - Semantic Search

Find files by meaning and concept, not just keyword matching.

**When to use:**
- User asks to find code related to a concept ("authentication", "payment processing", "data validation")
- Exploring an unfamiliar codebase to understand its structure
- Looking for examples of specific patterns or implementations
- Finding where a feature is implemented
- Investigating bugs or issues in a domain area

**How it works:**
- Searches by semantic meaning, not just exact text matches
- Returns ranked results with file paths, line ranges, and relevance scores
- Understands synonyms and related concepts (e.g., "login" finds "authentication" code)

**Best practices:**
- Use descriptive, conceptual queries: "user authentication flow" > "login function"
- Search broadly first, then narrow down with specific terms
- Combine multiple concepts: "database migration error handling"
- When grep returns too many results, use semantic search to find the most relevant files

**Example queries:**
- "How does authentication work in this codebase?"
- "Find all payment processing logic"
- "Where is data validation implemented?"
- "Show me error handling patterns"
- "Find files related to user session management"

### 2. `related` - Find Related Files

Discover files semantically related to a given file.

**When to use:**
- Editing a file and need to find its tests
- Understanding dependencies and connections
- Finding files that work together (models + controllers, components + styles)
- Discovering similar implementations or patterns
- Identifying impact areas before making changes

**How it works:**
- Analyzes semantic similarity to find related files
- Returns files that share concepts, patterns, or domain logic
- Helps map out architectural connections

**Best practices:**
- Use when viewing or editing a file to understand its context
- Check related files before modifying to understand impact
- Find tests by searching for related files to implementation
- Discover similar patterns to maintain consistency

**Example usage:**
- "What files are related to this authentication module?"
- "Find the tests for this payment service"
- "Show me other components that work with this API"

### 3. `summary` - File Index Metadata

Get information about a file's index status.

**When to use:**
- Checking if a file is indexed (troubleshooting)
- Understanding how a file is chunked
- Verifying index freshness after changes

**How it works:**
- Returns chunk count, types, and last indexed timestamp
- Confirms whether a file is in the searchable index

**Best practices:**
- Use sparingly - mainly for debugging
- If search isn't finding a file, check its summary to confirm it's indexed
- After major changes, verify the file was re-indexed

## Strategic Usage Patterns

### Pattern 1: Initial Codebase Exploration

When first encountering a codebase:

1. Ask broad conceptual questions to understand architecture
2. Use `search` to find entry points and main components
3. Use `related` on key files to map out connections
4. Build a mental model of the codebase structure

Example workflow:
```
search: "main application entry point"
search: "routing and request handling"
related: <key router file>
search: "database models and schemas"
```

### Pattern 2: Feature Investigation

When investigating how a feature works:

1. Search for the feature concept broadly
2. Examine top results to identify core files
3. Use `related` to find associated tests and dependencies
4. Search for specific sub-concepts as needed

Example workflow:
```
search: "user authentication and session management"
related: <main auth file>
search: "password reset flow"
```

### Pattern 3: Bug Investigation

When debugging an issue:

1. Search for the error domain or symptom
2. Use `related` to find connected code
3. Search for specific error patterns or edge cases
4. Examine test files to understand expected behavior

Example workflow:
```
search: "payment processing errors"
related: <payment service file>
search: "transaction rollback and retry logic"
```

### Pattern 4: Before Making Changes

Before modifying code:

1. Use `related` on the file you're editing
2. Check tests and dependent files
3. Search for similar patterns elsewhere in the codebase
4. Ensure consistency with existing implementations

Example workflow:
```
related: <file you're editing>
search: "similar validation patterns"
```

## Semantic Search vs. Traditional Search

**Use semantic search (semdex) when:**
- Looking for concepts, not exact strings
- Exploring unfamiliar code
- Finding implementations of features
- Understanding architecture and patterns
- Results from grep are too noisy or too sparse

**Use grep/find when:**
- Looking for exact function/variable names
- Finding all uses of a specific API
- Searching for literal strings or patterns
- You know exactly what you're looking for

## Proactive Usage

Don't wait for the user to ask you to search. When you need to understand code:

1. **Before reading multiple files**, search to identify the most relevant ones
2. **When user asks "how does X work"**, start with semantic search
3. **Before implementing features**, search for similar existing patterns
4. **When encountering unfamiliar code**, search to build context
5. **Before suggesting changes**, use `related` to understand impact

Remember: Semdex understands meaning, not just keywords. Ask conceptual questions and let the semantic search find the relevant code.

## Common Mistakes to Avoid

1. **Don't forget semdex exists** - Use it proactively, not as a fallback
2. **Don't use grep for conceptual queries** - "authentication code" is semantic, not literal
3. **Don't read files blindly** - Search first to identify relevant files
4. **Don't skip the `related` tool** - It reveals architectural connections
5. **Don't use keyword-only queries** - "login.py" is grep, "login flow" is semantic

## Quick Reference

| Task | Tool | Example |
|------|------|---------|
| Find code by concept | `search` | "error handling patterns" |
| Find tests for a file | `related` | related to auth_service.py |
| Find similar implementations | `search` + `related` | Search pattern, then related to result |
| Understand architecture | `search` | "main components and structure" |
| Check if file is indexed | `summary` | summary of file.py |

The key insight: **Semdex understands what code does, not just what it says**. Use it to navigate by meaning.
