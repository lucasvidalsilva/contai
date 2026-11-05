"use client";

import { useEffect, useState } from "react";

import { useInView, useReducedMotion } from "./hooks";

const format = new Intl.NumberFormat("pt-BR");

export function CountUp({ to }: { to: number }) {
	const [ref, inView] = useInView<HTMLSpanElement>(0.9);
	const reduced = useReducedMotion();
	const [value, setValue] = useState(0);

	useEffect(() => {
		if (!inView) return;
		if (reduced) {
			setValue(to);
			return;
		}
		let frame = 0;
		const start = performance.now();
		const duration = 1500;
		const tick = (now: number) => {
			const progress = Math.min((now - start) / duration, 1);
			setValue(Math.round(to * (1 - (1 - progress) ** 3)));
			if (progress < 1) frame = requestAnimationFrame(tick);
		};
		frame = requestAnimationFrame(tick);
		return () => cancelAnimationFrame(frame);
	}, [inView, reduced, to]);

	return <span ref={ref}>{format.format(value)}</span>;
}
