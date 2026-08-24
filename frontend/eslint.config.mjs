import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // This rule flags the standard "fetch on mount" pattern
      // (useEffect(() => { asyncFn() }, [])) even when the setState calls
      // inside asyncFn happen after an await, not synchronously in the
      // effect body. That's React's own documented pattern for fetching
      // data on mount (react.dev/reference/react/useEffect#fetching-data-with-effects),
      // and inline eslint-disable-next-line comments don't suppress this
      // rule's diagnostics, so it's disabled here instead of leaving a
      // broken suppression comment in the code.
      "react-hooks/set-state-in-effect": "off",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
