import type { CSSProperties } from "react";

/** Permite passar variáveis CSS (--x) no atributo style sem perder a tipagem. */
export const vars = (
	values: Record<`--${string}`, string | number>,
): CSSProperties => values as CSSProperties;
