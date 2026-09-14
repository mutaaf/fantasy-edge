// The few Node built-ins the tests use, declared here so the suite type-checks
// without adding @types/node. Tests run on Node's own TypeScript stripping.
declare module "node:test" {
  export function test(name: string, fn: () => void | Promise<void>): void;
  export function describe(name: string, fn: () => void): void;
}
declare module "node:assert/strict" {
  const assert: {
    (value: unknown, message?: string): asserts value;
    equal(actual: unknown, expected: unknown, message?: string): void;
    notEqual(actual: unknown, expected: unknown, message?: string): void;
    deepEqual(actual: unknown, expected: unknown, message?: string): void;
    ok(value: unknown, message?: string): asserts value;
    match(value: string, re: RegExp, message?: string): void;
    throws(fn: () => unknown, message?: string | RegExp): void;
  };
  export default assert;
}
declare module "node:fs" {
  export function readFileSync(path: string | URL, encoding: "utf8"): string;
}
declare const process: { env: Record<string, string | undefined> };
