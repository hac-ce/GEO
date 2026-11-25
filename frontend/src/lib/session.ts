// 令牌仅在当前标签页保存；每次请求仍由后端验证。
export function createSession(storage?: Pick<Storage, 'getItem'|'setItem'|'removeItem'>) {
  const key = 'geo.access-token';
  let token: string | null = null;
  try { token = storage?.getItem(key) ?? null; } catch { /* 存储禁用时使用内存。 */ }
  const listeners = new Set<() => void>();
  return {
    getToken: () => token,
    setToken(value: string | null) {
      token = value;
      try { if (value) storage?.setItem(key, value); else storage?.removeItem(key); } catch { /* 内存回退。 */ }
      listeners.forEach(listener => listener());
    },
    clearIfMatches(value: string | null) { if (token === value) this.setToken(null); },
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
  };
}
let storage: Storage | undefined;
try { if (typeof window !== 'undefined') storage = window.sessionStorage; } catch { /* 内存回退。 */ }
export const session = createSession(storage);
