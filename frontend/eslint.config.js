// Flat ESLint config: TypeScript + React hooks + jsx-a11y, plus (since
// E3-S4 adds `src/features/`) the "features do not import each other"
// `no-restricted-imports` rule from folder-structure.md's import-rules
// table: `features/*` may import `components`, `api`, `auth`, `lib`, but
// never another `features/*` module.
import js from "@eslint/js";
import globals from "globals";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";

export default [
  js.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...globals.browser,
        JSX: "readonly",
      },
    },
    plugins: {
      "@typescript-eslint": tseslint,
      "react-hooks": reactHooks,
      "jsx-a11y": jsxA11y,
    },
    rules: {
      ...tseslint.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.configs.recommended.rules,
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": "error",
      // TypeScript's own checker resolves ambient DOM lib types (e.g.
      // HeadersInit, RequestInit); no-undef doesn't know about them and
      // would otherwise false-positive on every TS-only type reference.
      "no-undef": "off",
    },
  },
  {
    // E3-S3 AC5's manually-triggered perf benchmark (specs/design/
    // deployment.md): a plain Node.js script, not a browser-targeted
    // module like the rest of this project, so it needs Node globals
    // (`process`, `console`) instead of `globals.browser`.
    files: ["e2e/perf/**/*.mjs"],
    languageOptions: {
      globals: { ...globals.node },
    },
  },
  {
    files: ["src/features/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["**/features/*"],
              message:
                "features do not import each other (folder-structure.md): import components, api, auth or lib instead.",
            },
          ],
        },
      ],
    },
  },
  {
    ignores: ["dist/**", "node_modules/**"],
  },
];
