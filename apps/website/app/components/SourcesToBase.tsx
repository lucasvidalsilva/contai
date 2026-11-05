"use client";

import { useEffect, useState } from "react";

import { useInView, useReducedMotion } from "./hooks";
import { vars } from "./utils";

const sources = [
	{
		name: "Tabela NCM",
		about: "Classificação de mercadorias",
		x: -46,
		y: -14,
		r: -3.2,
	},
	{ name: "TIPI", about: "Alíquotas de IPI por NCM", x: 38, y: 10, r: 2.4 },
	{ name: "CEST", about: "Substituição tributária", x: -22, y: 18, r: 1.6 },
	{
		name: "IBS e CBS",
		about: "Tabelas da reforma tributária",
		x: 52,
		y: -12,
		r: -2.1,
	},
	{
		name: "LC 214",
		about: "Lei complementar da reforma",
		x: -40,
		y: 6,
		r: 2.8,
	},
	{ name: "Atos CONFAZ", about: "Convênios e ajustes", x: 30, y: -8, r: -1.6 },
];

export function SourcesToBase() {
	const [ref, inView] = useInView<HTMLDivElement>(0.6);
	const [merged, setMerged] = useState(false);
	const reduced = useReducedMotion();

	// As fontes se reúnem sozinhas na primeira vez que a área aparece.
	useEffect(() => {
		if (!inView) return;
		if (reduced) {
			setMerged(true);
			return;
		}
		const timer = setTimeout(() => setMerged(true), 1400);
		return () => clearTimeout(timer);
	}, [inView, reduced]);

	return (
		<div className="desk-wrap">
			<div className="desk" data-merged={merged} ref={ref}>
				<p className="desk__base" aria-hidden="true">
					<span>Base contAI</span>
					<span>origem, captura, vigência e versão em cada linha</span>
				</p>
				<ul className="desk__list">
					{sources.map((source, index) => (
						<li
							className="paper"
							key={source.name}
							style={vars({
								"--x": `${source.x}px`,
								"--y": `${source.y}px`,
								"--r": `${source.r}deg`,
								"--i": index,
							})}
						>
							<span className="paper__name">{source.name}</span>
							<span className="paper__about">{source.about}</span>
							<span className="paper__state" aria-hidden="true">
								na base
							</span>
						</li>
					))}
				</ul>
			</div>
			<button
				aria-pressed={merged}
				className="text-button"
				onClick={() => setMerged((value) => !value)}
				type="button"
			>
				{merged ? "Espalhar de novo" : "Reunir as fontes"}
			</button>
		</div>
	);
}
