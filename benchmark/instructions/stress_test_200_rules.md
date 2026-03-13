# Coding Agent Instructions — Stress Test (200 rules)

These rules intentionally vary in style, verbosity, and category to stress-test
MCP graph construction and retrieval fidelity versus plain-markdown injection.

---

## 1. Validation & Testing

1. Always run the test suite before declaring a task complete.
2. Never mark a task as done if any test is failing.
3. Run linting after every code change.
4. Typecheck before submitting — `tsc --noEmit` or equivalent.
5. If tests don't exist, write at least one smoke test covering the happy path.
6. Do not skip tests with `.skip` or `xit` unless explicitly asked.
7. When adding a new function, add a unit test for it.
8. Integration tests take priority over unit tests when both exist.
9. Always check that your change doesn't break unrelated tests.
10. Run only the tests relevant to the changed files when possible to save time.

---

## 2. Minimal Change

11. Change the fewest lines necessary to accomplish the task.
12. Do not refactor surrounding code unless the task explicitly requires it.
13. Do not rename variables you didn't need to rename.
14. Avoid adding new dependencies for things achievable with existing libraries.
15. Never rewrite a file from scratch when a small edit suffices.
16. Don't add comments to code you didn't change.
17. Preserve the original indentation and formatting style of each file.
18. Don't upgrade package versions unless that is the task.
19. Avoid adding new exports from a module unless required.
20. If a helper function already exists, use it — don't duplicate it.

---

## 3. Git & Branch Discipline

21. Never commit directly to main or master.
22. Create a feature branch for every new task.
23. Branch names should follow the pattern `feat/<short-description>` or `fix/<short-description>`.
24. Keep commits small and focused — one logical change per commit.
25. Write clear commit messages: imperative mood, under 72 characters in the subject line.
26. Do not force-push to shared branches.
27. Never use `git reset --hard` without explicit user approval.
28. Don't squash commits unless asked.
29. Stage only the files related to your change — avoid `git add .` blindly.
30. Always `git pull --rebase` before pushing to avoid unnecessary merge commits.

---

## 4. File & Workspace Safety

31. Do not delete files unless explicitly instructed.
32. Never overwrite a file the user has manually edited in this session.
33. Before creating a new file, check whether a suitable one already exists.
34. Do not write to files under `protected/` or `benchmark/tasks/`.
35. Never modify `.env` or `.env.*` files.
36. Do not read secrets from environment variables and log them.
37. Keep generated files out of version control unless the project already does so.
38. Do not write temporary debug files to the repository root.
39. If you need a scratch file, use the system temp directory.
40. Always check that a file path exists before attempting to read it.

---

## 5. Security

41. Never hardcode API keys, passwords, or tokens in source code.
42. Use environment variables for all secrets.
43. Do not log sensitive data such as passwords, tokens, or PII.
44. Sanitize all user-provided input before using it in shell commands.
45. Never construct SQL queries by string concatenation — use parameterized queries.
46. Do not expose stack traces to end users in API responses.
47. Avoid storing passwords in plain text — always hash with bcrypt or argon2.
48. Validate all external API responses before trusting them.
49. Don't include secrets in commit messages or PR descriptions.
50. Use HTTPS for all outbound HTTP requests; never downgrade to HTTP silently.

---

## 6. Code Style — General

51. Use meaningful variable names — single letters only for loop indices.
52. Keep functions under 40 lines; extract helpers when they grow longer.
53. Avoid deeply nested conditionals — use early returns.
54. Prefer explicit over implicit — don't rely on type coercion.
55. Don't leave commented-out code in the codebase.
56. Prefer immutable data structures where practical.
57. Use constants for magic numbers and strings.
58. Functions should do one thing.
59. Avoid global mutable state.
60. Don't use `any` as a type annotation unless absolutely unavoidable.

---

## 7. TypeScript Specifics

61. Enable `strict` mode in tsconfig — do not disable it.
62. Prefer `interface` over `type` for object shapes that may be extended.
63. Use `type` for unions, intersections, and aliases.
64. Never use `as unknown as X` casts without a comment explaining why.
65. Annotate function return types explicitly on public APIs.
66. Don't use `!` non-null assertion unless you can prove the value is set.
67. Prefer `readonly` on arrays and object properties when mutation isn't needed.
68. Use `satisfies` operator to validate object literals against a type without widening.
69. Avoid `enum` — prefer `as const` object maps.
70. Use `unknown` instead of `any` for values from external sources.

---

## 8. React Specifics

71. Don't call hooks conditionally or inside loops.
72. Use `useCallback` for handlers passed as props to memo components.
73. Use `useMemo` only when the computation is measurably expensive.
74. Never mutate state directly — always return a new value from setState.
75. Prefer controlled components over uncontrolled for form inputs.
76. Clean up side effects in `useEffect` by returning a cleanup function.
77. Avoid placing business logic inside JSX — extract to functions.
78. Don't use `index` as a key when the list can be reordered.
79. Keep components focused — split when a component has more than ~150 lines of JSX.
80. Use React Error Boundaries around third-party or async-heavy subtrees.

---

## 9. API Design

81. All API endpoints must return JSON.
82. Use HTTP status codes correctly — 404 for not-found, 422 for validation errors, 500 for unhandled server errors.
83. Never return a 200 response with an `error` field to indicate failure.
84. Paginate list endpoints — do not return unbounded arrays.
85. Version your API — all routes should be under `/api/v1/` or similar.
86. Validate incoming request bodies before processing.
87. Include a `requestId` in all error responses for traceability.
88. Don't expose internal database IDs in public API responses — use slugs or opaque IDs.
89. Idempotency: PUT and PATCH endpoints must be safe to retry.
90. Document new endpoints in the OpenAPI spec if one exists.

---

## 10. Error Handling

91. Never swallow errors silently — at minimum, log them.
92. Use typed error classes rather than throwing plain strings.
93. Distinguish between expected errors (validation, not-found) and unexpected ones (bugs).
94. Don't catch and rethrow without adding context.
95. In async functions, always handle both the resolved value and the rejection.
96. Never use `try/catch` around entire functions to hide bugs.
97. When catching errors from external APIs, include the original status code in your error.
98. Log errors with stack traces in development; omit stacks in production client responses.
99. Fail fast — validate preconditions at the top of a function.
100. Use `finally` blocks only for cleanup, not for control flow.

---

## 11. Performance

101. Avoid N+1 queries — batch database lookups.
102. Cache expensive computations at the call site, not inside the function.
103. Don't block the event loop with synchronous file I/O in Node.js.
104. Use streaming for large file uploads/downloads.
105. Index database columns used in `WHERE` and `ORDER BY` clauses.
106. Avoid loading entire tables into memory — paginate or stream.
107. Profile before optimizing — don't assume where the bottleneck is.
108. Use connection pooling for database access.
109. Debounce or throttle user-triggered search/filter calls on the frontend.
110. Lazy-load images and heavy components.

---

## 12. Documentation

111. Write a JSDoc/docstring for every public function.
112. Update the README if you add or remove a CLI flag or configuration option.
113. Add inline comments only where the logic is non-obvious.
114. Don't write comments that just restate what the code does.
115. Keep the CHANGELOG updated when making user-facing changes.
116. Document required environment variables in `.env.example`.
117. When deprecating a function, add a `@deprecated` annotation with a migration path.
118. Architecture decisions should be recorded in ADR files if the project uses them.
119. Include usage examples in docstrings for utility functions.
120. Don't leave TODO comments without a linked issue number.

---

## 13. Database

121. Never run raw `DROP TABLE` or `DELETE` without a `WHERE` clause in migration scripts.
122. All schema changes must go through migration files — no manual DB edits.
123. Make migrations reversible where possible (include a `down` migration).
124. Don't load more columns than needed — avoid `SELECT *` in production queries.
125. Use transactions for multi-step writes.
126. Always index foreign key columns.
127. Soft-delete by setting `deleted_at` rather than hard-deleting records.
128. Don't store binary blobs in the database — use object storage and store the URL.
129. Avoid long-running transactions that hold locks.
130. Test migrations on a copy of production data before applying to prod.

---

## 14. Tooling & Commands

131. Never run `rm -rf` without explicit user approval.
132. Avoid `--force` flags on git commands unless you understand the consequences.
133. Don't run `npm install` or `bun install` mid-task unless dependencies have changed.
134. Prefer `bun` over `npm` or `yarn` in this monorepo.
135. Use `npx` for one-off CLI tools rather than installing them globally.
136. Don't pipe curl to bash.
137. Confirm before running any command that modifies the database.
138. Use `--dry-run` flags when available before executing destructive scripts.
139. Always read the help text of an unfamiliar CLI tool before using it.
140. Don't run build steps on every file-save during development — use watch mode.

---

## 15. Behavior & Communication

141. Don't ask clarifying questions for information already present in the task description.
142. If a requirement is ambiguous, state your assumption and proceed.
143. Don't announce every small action — summarize what you did at the end.
144. If you encounter a blocker, explain it clearly rather than silently skipping the step.
145. Don't apologize repeatedly — fix the problem instead.
146. When estimating scope, be conservative.
147. Prefer doing the task over explaining how to do it, unless explanation is requested.
148. If you identify a related bug while working, note it but don't fix it unless asked.
149. Always confirm before making changes outside the files specified in the task.
150. Keep responses focused on what changed — don't restate unchanged context.

---

## 16. Monorepo & Package Management

151. Changes to `packages/shared` affect all consuming apps — test all of them.
152. Don't add a package to the root `package.json` if it's only needed in one app.
153. Keep devDependencies out of `dependencies`.
154. When two packages depend on the same library, hoist it to the workspace root.
155. Don't introduce circular imports between packages.
156. Run `bun run typecheck` from the repo root after changing shared types.
157. Use path aliases (`@/`) instead of deep relative imports.
158. Don't import from a package's internal paths — use its public API only.
159. Avoid large barrel files (`index.ts` that re-exports everything).
160. When removing a dependency, verify it's not used transitively.

---

## 17. Accessibility

161. All interactive elements must be keyboard-navigable.
162. Images must have meaningful `alt` text.
163. Decorative images must use `alt=""`.
164. Color alone must not convey information.
165. Minimum contrast ratio is 4.5:1 for normal text.
166. Form inputs must have associated `<label>` elements.
167. Error messages must be programmatically associated with their input fields.
168. Modal dialogs must trap focus and restore focus on close.
169. Don't use `tabIndex` values greater than 0.
170. Ensure all ARIA roles are used correctly — don't add ARIA where native HTML suffices.

---

## 18. Miscellaneous / Overlapping (intentionally messy)

171. Before writing any code, read the relevant existing code first.
172. never use console.log in production code paths.
173. Prefer async/await over raw .then() chains.
174. Do not nest more than 3 levels of callbacks.
175. A function named `getX` should return X, not modify state as a side effect.
176. Keep business logic out of route handlers — put it in service or repository layers.
177. validate before concluding — run all checks before saying the task is done.
178. Always validate user input at the API boundary, even if the frontend also validates.
179. Avoid `eval()` and `new Function()`.
180. don't import the entire lodash library — import only the functions you need.
181. Prefer `structuredClone` over `JSON.parse(JSON.stringify(...))` for deep clones.
182. When writing a loop, consider whether `map`, `filter`, or `reduce` is clearer.
183. Don't use `setTimeout(fn, 0)` to defer work — use `queueMicrotask` or a proper task queue.
184. Keep CSS class names semantic — avoid names like `div2` or `wrapper3`.
185. Avoid inline styles except for dynamically computed values.
186. Use CSS variables (custom properties) for design tokens.
187. Don't load fonts from external CDNs in a production bundle — self-host them.
188. Compress images before committing them to the repository.
189. Use SVG for icons rather than icon fonts.
190. Prefer native browser APIs over polyfills when browser support allows.

---

## 19. Contradictory / Tricky Rules (for conflict detection testing)

191. Prefer small, frequent commits over large batches.
192. Prefer large, complete commits over incremental WIP commits. *(conflicts with 191)*
193. Always write unit tests for utility functions.
194. Utility functions are simple enough to not need tests — skip them. *(conflicts with 193)*
195. Use `console.error` for error logging in Node.js services.
196. Never use `console.*` in any production code — use a structured logger. *(conflicts with 195)*
197. When in doubt, add a comment explaining the code.
198. Comments are a code smell — rewrite the code to be self-explanatory instead. *(conflicts with 197)*
199. Return early from functions to reduce nesting.
200. Avoid early returns — they make control flow harder to follow. *(conflicts with 199)*
