type ProcessLike = {
  env: Record<string, string | undefined>;
};

const runtimeProcess = (globalThis as { process?: ProcessLike }).process;

export function readEnv(name: string): string | undefined {
  return runtimeProcess?.env[name];
}
