"use client";

import { useEffect, useRef, useState } from "react";

import { type AssistantId, Glyph, GlyphIcon } from "./glyphs";
import { useInView, useReducedMotion } from "./hooks";
import { vars } from "./utils";

const assistants: { id: AssistantId; name: string; via: string; cy: number }[] =
	[
		{
			id: "chatgpt",
			name: "ChatGPT",
			via: "Integração candidata. Compatibilidade e requisitos de plano ainda não validados.",
			cy: 48,
		},
		{
			id: "gemini",
			name: "Gemini",
			via: "Integração candidata. Autenticação e formato de conexão ainda não definidos.",
			cy: 150,
		},
		{
			id: "claude",
			name: "Claude",
			via: "Integração candidata. Nenhuma conexão de ponta a ponta foi testada.",
			cy: 252,
		},
	];

const wirePath = (cy: number) =>
	cy === 150 ? "M80 150 L206 150" : `M80 ${cy} C 150 ${cy}, 140 150, 206 150`;
const BASE_PATH = "M306 150 L370 150";

type ChatItem =
	| { id: string; kind: "user"; text: string }
	| {
			id: string;
			kind: "tool";
			name: string;
			args: string;
			result: [string, string][];
	  }
	| { id: string; kind: "assistant"; text: string; source: string };

const script: ChatItem[] = [
	{
		id: "q1",
		kind: "user",
		text: "O NCM 2203.00.00 consta no snapshot observado em 30/10/2026?",
	},
	{
		id: "t1",
		kind: "tool",
		name: "contrato ilustrativo · consultar referência",
		args: 'codigo: "2203.00.00", data_coberta: "2026-10-30"',
		result: [
			["descricao", "Cervejas de malte"],
			["resultado", "presente no snapshot coberto"],
			["fonte", "Portal Único Siscomex"],
			["cobertura", "30/10/2026"],
			["release", "identificada por SHA-256"],
		],
	},
	{
		id: "a1",
		kind: "assistant",
		text: "Sim. O código 2203.00.00 aparece no snapshot cuja cobertura é 30/10/2026. A release e o arquivo de origem são identificados por SHA-256 para permitir repetição da consulta.",
		source: "Portal Único Siscomex · snapshot coberto em 30/10/2026",
	},
	{
		id: "q2",
		kind: "user",
		text: "Isso prova que o código valia em 15/03/2024?",
	},
	{
		id: "t2",
		kind: "tool",
		name: "contrato ilustrativo · verificar cobertura",
		args: 'data_operacao: "2024-03-15"',
		result: [
			["snapshot", "cobre somente 30/10/2026"],
			["data pedida", "15/03/2024"],
			["conclusao", "não extrapolar historicamente"],
		],
	},
	{
		id: "a2",
		kind: "assistant",
		text: "Não. O snapshot atual só sustenta uma conclusão para a data coberta. Para 15/03/2024, a resposta correta é declarar a lacuna e buscar uma versão histórica verificável.",
		source: "Limite temporal declarado pelo catálogo NCM",
	},
];

// Pausa antes de cada item aparecer, em milissegundos.
const gaps = [300, 900, 2100, 4200, 900, 2100];

function Streamed({ text, instant }: { text: string; instant: boolean }) {
	const words = text.split(" ");
	const [count, setCount] = useState(instant ? words.length : 0);

	useEffect(() => {
		const total = text.split(" ").length;
		if (instant) {
			setCount(total);
			return;
		}
		const timer = setInterval(() => {
			setCount((value) => {
				if (value >= total) {
					clearInterval(timer);
					return value;
				}
				return value + 1;
			});
		}, 42);
		return () => clearInterval(timer);
	}, [instant, text]);

	return <>{words.slice(0, count).join(" ")}</>;
}

function ToolCall({
	item,
	instant,
}: {
	item: Extract<ChatItem, { kind: "tool" }>;
	instant: boolean;
}) {
	const [done, setDone] = useState(instant);

	useEffect(() => {
		if (instant) {
			setDone(true);
			return;
		}
		const timer = setTimeout(() => setDone(true), 1000);
		return () => clearTimeout(timer);
	}, [instant]);

	return (
		<div className="tool" data-done={done}>
			<div className="tool__head">
				<span aria-hidden="true" className="tool__dot" />
				<code>{item.name}</code>
				<span className="tool__state">
					{done ? "concluído" : "consultando"}
				</span>
			</div>
			<code className="tool__args">{item.args}</code>
			{done && (
				<dl className="tool__result">
					{item.result.map(([key, value], index) => (
						<div key={key} style={vars({ "--i": index })}>
							<dt>{key}</dt>
							<dd>{value}</dd>
						</div>
					))}
				</dl>
			)}
		</div>
	);
}

function Conversation({ instant }: { instant: boolean }) {
	const [shown, setShown] = useState(instant ? script.length : 0);
	const bodyRef = useRef<HTMLDivElement>(null);
	const flowRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		if (instant) {
			setShown(script.length);
			return;
		}
		const timers: number[] = [];
		let elapsed = 0;
		script.forEach((item, index) => {
			elapsed += gaps[index] ?? 1000;
			timers.push(window.setTimeout(() => setShown(index + 1), elapsed));
			void item;
		});
		return () => {
			for (const timer of timers) window.clearTimeout(timer);
		};
	}, [instant]);

	// Mantém a conversa rolada até o fim enquanto o texto cresce.
	useEffect(() => {
		const body = bodyRef.current;
		const flow = flowRef.current;
		if (!body || !flow) return;
		const observer = new ResizeObserver(() =>
			body.scrollTo({ top: body.scrollHeight }),
		);
		observer.observe(flow);
		return () => observer.disconnect();
	}, []);

	return (
		<div
			className="chat__body"
			ref={bodyRef}
			role="log"
			aria-live="off"
			aria-label="Simulação de conversa"
		>
			<div className="chat__flow" ref={flowRef}>
				{script.slice(0, shown).map((item) => {
					if (item.kind === "user") {
						return (
							<p className="msg msg--user" key={item.id}>
								{item.text}
							</p>
						);
					}
					if (item.kind === "tool") {
						return <ToolCall instant={instant} item={item} key={item.id} />;
					}
					return (
						<div className="msg msg--assistant" key={item.id}>
							<p>
								<Streamed instant={instant} text={item.text} />
							</p>
							<span className="msg__source">Fonte: {item.source}</span>
						</div>
					);
				})}
			</div>
		</div>
	);
}

function Packets({
	path,
	dur,
	offsets,
}: {
	path: string;
	dur: number;
	offsets: number[];
}) {
	return (
		<>
			{offsets.map((offset) => (
				<circle className="packet" key={offset} r="3.4">
					<animateMotion
						begin={`${offset}s`}
						dur={`${dur}s`}
						path={path}
						repeatCount="indefinite"
					/>
				</circle>
			))}
		</>
	);
}

export function Connector() {
	const [active, setActive] = useState<AssistantId>("claude");
	const [run, setRun] = useState(0);
	const [ref, inView] = useInView<HTMLDivElement>(0.3);
	const reduced = useReducedMotion();
	const current =
		assistants.find((item) => item.id === active) ?? assistants[2];

	const select = (id: AssistantId) => {
		setActive(id);
		setRun((value) => value + 1);
	};

	return (
		<div className="connector" ref={ref}>
			<div className="connector__diagram">
				<svg viewBox="0 0 440 300">
					<title>
						Assistentes de IA ligados ao conector do contAI e à base pública
					</title>
					{assistants.map((item) => (
						<path
							className="wire"
							d={wirePath(item.cy)}
							data-on={item.id === active}
							key={item.id}
						/>
					))}
					<path className="wire wire--out" d={BASE_PATH} />

					{!reduced && (
						<>
							<Packets
								dur={1.9}
								offsets={[0, 0.95]}
								path={wirePath(current.cy)}
							/>
							<Packets dur={1.4} offsets={[0.2, 0.9]} path={BASE_PATH} />
						</>
					)}

					<g className="hub">
						<rect height="120" rx="10" width="100" x="206" y="90" />
						<path d="M231 118h30M231 128h20M231 138h30" />
						<circle cx="262" cy="128" r="3.4" />
						<text x="256" y="168">
							contAI
						</text>
						<text className="hub__sub" x="256" y="186">
							conector
						</text>
						<text className="caption" x="256" y="232">
							somente leitura
						</text>
					</g>

					<g className="base">
						{[100, 137, 174].map((y) => (
							<rect height="26" key={y} rx="5" width="58" x="370" y={y} />
						))}
						<text className="caption" x="399" y="222">
							base pública
						</text>
					</g>

					<g>
						{assistants.map((item) => (
							<g className="node" data-on={item.id === active} key={item.id}>
								<circle cx="54" cy={item.cy} r="27" />
								<g transform={`translate(${54 - 12} ${item.cy - 12})`}>
									<Glyph id={item.id} />
								</g>
								<text x="54" y={item.cy + 46}>
									{item.name}
								</text>
							</g>
						))}
					</g>
				</svg>

				<div className="via">
					{assistants.map((item) => (
						<button
							aria-pressed={item.id === active}
							className="via__option"
							data-on={item.id === active}
							key={item.id}
							onClick={() => select(item.id)}
							type="button"
						>
							<strong>{item.name}</strong>
							<span>{item.via}</span>
						</button>
					))}
				</div>
				<p className="via__note">
					Nomes e símbolos identificam integrações candidatas. Não representam
					compatibilidade, parceria ou disponibilidade atual.
				</p>
			</div>

			<div className="chat" data-assistant={active}>
				<div className="chat__head">
					<span className="chat__glyph">
						<GlyphIcon id={active} size={18} />
					</span>
					<strong>{current.name}</strong>
					<span className="chat__status">
						<span aria-hidden="true" /> simulação em execução
					</span>
				</div>
				{inView && <Conversation instant={reduced} key={`${active}-${run}`} />}
				{!inView && <div className="chat__body" />}
				<div className="chat__foot">
					<span>Simulação de contrato. O conector ainda não existe.</span>
					<button
						className="text-button text-button--light"
						onClick={() => setRun((value) => value + 1)}
						type="button"
					>
						Repetir
					</button>
				</div>
			</div>
		</div>
	);
}
