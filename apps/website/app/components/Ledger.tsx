import { vars } from "./utils";

const rows = [
	{
		id: "1",
		ncm: "2203.00.00",
		desc: "Cerveja de malte, lata 350 ml, caixa com 12",
		value: "1.248,00",
	},
	{
		id: "2",
		ncm: "2201.10.00",
		desc: "Água mineral, garrafa 1,5 L, fardo com 6",
		value: "312,50",
	},
	{
		id: "3",
		ncm: "2202.99.00",
		desc: "Bebida não alcoólica, 2 L, fardo com 6",
		value: "489,50",
	},
];

const Tick = () => (
	<svg aria-hidden="true" className="tick" fill="none" viewBox="0 0 20 20">
		<path d="M3.5 10.5 8 15l8.5-10" pathLength={1} />
	</svg>
);

/**
 * Folha de conferência: a sequência de entrada (réguas, itens, vistos,
 * sublinhado duplo do total e o círculo no valor divergente) roda uma vez
 * ao carregar. As datas ficam em --d, em segundos.
 */
export function Ledger() {
	return (
		<figure className="ledger" aria-labelledby="ledger-title">
			<figcaption className="ledger__bar" id="ledger-title">
				<span>NF-e modelo 55</span>
				<span className="ledger__badge">exemplo ilustrativo</span>
			</figcaption>

			<table className="ledger__table">
				<caption className="visually-hidden">
					Itens de uma NF-e de exemplo e a conferência do total informado
				</caption>
				<thead>
					<tr>
						<th
							aria-label="Conferência"
							className="ledger__tick-col"
							scope="col"
						/>
						<th scope="col">NCM</th>
						<th scope="col">Descrição</th>
						<th className="num" scope="col">
							vProd (R$)
						</th>
					</tr>
				</thead>
				<tbody>
					{rows.map((row, index) => (
						<tr
							key={row.id}
							style={vars({
								"--d": `${0.55 + index * 0.2}s`,
								"--t": `${1.35 + index * 0.28}s`,
							})}
						>
							<td className="ledger__tick-col">
								<Tick />
							</td>
							<td className="mono">{row.ncm}</td>
							<td>{row.desc}</td>
							<td className="num mono">{row.value}</td>
						</tr>
					))}
				</tbody>
				<tfoot>
					<tr className="ledger__sum" style={vars({ "--d": "2.3s" })}>
						<td className="ledger__tick-col" />
						<th colSpan={2} scope="row">
							Soma dos itens
						</th>
						<td className="num mono">
							<span className="ledger__total">2.050,00</span>
						</td>
					</tr>
					<tr className="ledger__declared" style={vars({ "--d": "2.7s" })}>
						<td className="ledger__tick-col" />
						<th colSpan={2} scope="row">
							Total informado na nota (ICMSTot/vProd)
						</th>
						<td className="num mono">
							<span className="ledger__circled">
								2.051,00
								<svg
									aria-hidden="true"
									className="circle"
									fill="none"
									viewBox="0 0 120 48"
									preserveAspectRatio="none"
								>
									<path
										d="M16 9C40 1 98 2 112 14c9 9-4 26-34 31C46 50 6 44 5 27 4 15 20 6 52 4"
										pathLength={1}
									/>
								</svg>
							</span>
						</td>
					</tr>
				</tfoot>
			</table>

			<p className="ledger__note" style={vars({ "--d": "3.2s" })}>
				<strong>Regra W07.</strong> O total informado difere da soma dos itens
				em R$ 1,00. O contAI mostra o campo, o valor e a regra. Quem decide é o
				contador.
			</p>
			<p className="ledger__legend">
				<svg
					aria-hidden="true"
					className="tick tick--static"
					fill="none"
					viewBox="0 0 20 20"
				>
					<path d="M3.5 10.5 8 15l8.5-10" />
				</svg>
				NCM conferido na tabela vigente na data da operação
			</p>
		</figure>
	);
}
