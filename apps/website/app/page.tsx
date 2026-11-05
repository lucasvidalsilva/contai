import { Connector } from "./components/Connector";
import { CountUp } from "./components/CountUp";
import { Ledger } from "./components/Ledger";
import { SourcesToBase } from "./components/SourcesToBase";
import { vars } from "./components/utils";

const REPO_URL = "https://github.com/lucasvidalsilva/contai";

const deliveryProof = [
	["06", "fontes oficiais com execução verde"],
	["34", "payloads brutos preservados e verificados"],
	["12.966", "blocos legais estruturados em staging privado"],
	["07", "verificações fiscais determinísticas na v1"],
];

const Mark = () => (
	<svg aria-hidden="true" className="mark" viewBox="0 0 64 64">
		<rect fill="currentColor" height="64" rx="14" width="64" />
		<path
			d="M17 21h30M17 32h21M17 43h30"
			stroke="var(--canvas)"
			strokeLinecap="round"
			strokeWidth="5"
		/>
		<circle cx="45" cy="32" fill="var(--blue)" r="5" />
	</svg>
);

const translation = [
	{
		desk: "Saber o que valia na data da operação",
		product:
			"Vigência e captura são campos distintos; quando a fonte não sustenta uma data, a lacuna fica explícita.",
	},
	{
		desk: "Mostrar de onde veio o número",
		product:
			"O endereço da fonte, o instante da captura e a integridade do arquivo ficam registrados.",
	},
	{
		desk: "Refazer a conferência meses depois",
		product:
			"O motor usa versões identificadas de dados e regras para que a execução possa ser repetida.",
	},
	{
		desk: "Assinar a conclusão",
		product:
			"O contAI organiza o que merece atenção. O julgamento e a assinatura continuam com o profissional.",
	},
];

const flow = [
	{
		name: "Fonte oficial",
		text: "Páginas e arquivos públicos, sem corpus de terceiros.",
	},
	{
		name: "Python",
		text: "Captura, parsing e normalização com contratos testados.",
	},
	{
		name: "Bronze",
		text: "Original imutável, URL, instante de captura e SHA-256.",
	},
	{
		name: "Qualidade",
		text: "Schema, volume, idempotência e falhas antes da publicação.",
	},
	{
		name: "PostgreSQL",
		text: "Staging privado e releases aprovadas no Supabase.",
	},
	{
		name: "Produto",
		text: "Motor fiscal local e interface apoiados no mesmo contrato.",
	},
];

const baseStatus = [
	{
		source: "Tabela NCM",
		state: "publicado",
		note: "15.157 registros; 10.516 códigos folha.",
	},
	{
		source: "TIPI",
		state: "publicado",
		note: "11.103 itens normalizados e versionados.",
	},
	{
		source: "IBS e CBS",
		state: "publicado",
		note: "18 CST, 173 classificações e 4.728 vínculos.",
	},
	{
		source: "CEST",
		state: "privado",
		note: "1.569 candidatos unresolved; sem publicação.",
	},
	{
		source: "LC 214",
		state: "staging",
		note: "Quatro registros estruturados, sem interpretação jurídica.",
	},
	{
		source: "24 atos CONFAZ",
		state: "staging",
		note: "2.776 blocos capturados a partir de remissões oficiais.",
	},
];

const principles = [
	[
		"Procedência",
		"URL de origem, identificador da fonte, instante da captura e integridade do conteúdo.",
	],
	[
		"Temporalidade",
		"A vigência legal fica separada da data em que o dado foi observado.",
	],
	[
		"Reprodutibilidade",
		"Toda conferência indica as versões de dados e de regras que usou.",
	],
	[
		"Qualidade",
		"Cargas idempotentes, validações, tratamento de falhas e monitoramento.",
	],
	[
		"Acesso governado",
		"APIs de leitura com permissões limitadas. Nenhuma chave administrativa vai para o cliente.",
	],
];

const connectorContract = [
	{
		name: "Consultar referência",
		ask: "Este NCM consta no snapshot coberto?",
		returns: "Resultado, fonte, data coberta e identificador da release.",
	},
	{
		name: "Localizar norma",
		ask: "Quais trechos oficiais mencionam este tema?",
		returns: "Texto literal, ato de origem e limite de interpretação.",
	},
	{
		name: "Descrever cobertura",
		ask: "Até onde esta base permite concluir?",
		returns: "Estado da fonte, última captura e lacunas conhecidas.",
	},
];

const steps = [
	"A pergunta vira uma consulta somente de leitura sobre uma release aprovada.",
	"O retorno inclui a evidência e declara a cobertura temporal disponível.",
	"O assistente responde sem transformar ausência de dado em conclusão fiscal.",
];

const guardrails = [
	[
		"Privilégio mínimo",
		"O aplicativo não receberá chaves privilegiadas do Supabase.",
	],
	[
		"Versões autenticadas",
		"As referências fiscais são verificadas antes de qualquer uso.",
	],
	[
		"IA opcional e explícita",
		"Qualquer integração futura com provedor externo deverá depender de ação explícita e fluxo documentado.",
	],
	[
		"LGPD",
		"O processamento local reduz a exposição, mas não dispensa proteção do dispositivo, atualizações e política de retenção.",
	],
];

const roadmap = [
	{
		name: "Pipeline tributária",
		state: "done",
		label: "Marco concluído",
		text: "Seis fontes públicas extraídas, validadas e versionadas no Supabase, com a procedência registrada. Ambiente de desenvolvimento.",
	},
	{
		name: "Motor fiscal",
		state: "done",
		label: "Concluído na v1",
		text: "Validação offline contra o XSD oficial, regras I11-10, I11-20, W07 a W10 e W15, catálogo NCM com limite temporal explícito e testes de regressão.",
	},
	{
		name: "Landing page",
		state: "doing",
		label: "Validação local",
		text: "Narrativa, componentes interativos, responsividade e acessibilidade. Preview público ainda depende de publicação autorizada.",
	},
	{
		name: "Aplicativo para Windows",
		state: "planned",
		label: "Em desenvolvimento",
		text: "Conferência local de lotes de NF-e com Tauri, React e TypeScript. O histórico fica em SQLite, no seu computador.",
	},
	{
		name: "Conector de IA",
		state: "planned",
		label: "Planejado",
		text: "Contrato somente de leitura sobre a base pública. Nenhuma integração com assistentes foi validada ou publicada.",
	},
];

const faq = [
	{
		q: "O que funciona hoje?",
		a: "A pipeline de seis fontes roda em GitHub Actions e persiste versões no Supabase de desenvolvimento. O motor fiscal valida NF-e modelo 55 offline e executa sete verificações determinísticas com testes. O aplicativo desktop e o conector ainda não foram implementados.",
	},
	{
		q: "A IA lê as notas fiscais dos meus clientes?",
		a: "Não no desenho atual. O conector previsto expõe somente referências tributárias públicas. A conferência padrão foi projetada para manter o XML no computador, e qualquer integração externa futura terá de ser explícita.",
	},
	{
		q: "Por que a IA não foi construída primeiro?",
		a: "Porque uma resposta convincente sem dado confiável continua sendo uma resposta frágil. O projeto priorizou procedência, temporalidade, idempotência, regras reproduzíveis e limites explícitos antes de desenhar a camada de IA.",
	},
	{
		q: "ChatGPT, Gemini e Claude já estão conectados?",
		a: "Não. A conversa mostrada nesta página é uma simulação de contrato. Compatibilidade, autenticação, nomes de consultas e requisitos de plano só serão divulgados depois de implementação e teste de ponta a ponta.",
	},
	{
		q: "A ausência de alerta quer dizer que a nota está em conformidade?",
		a: "Não. O contAI é uma ferramenta de apoio. Ele cobre as regras implementadas e informa os limites de cada conferência.",
	},
	{
		q: "Quando o contAI sai?",
		a: "Ainda não há data de distribuição. A próxima etapa de produto é o aplicativo para Windows; até lá, o repositório mostra o que foi implementado, como foi testado e quais limites permanecem.",
	},
];

export default function Home() {
	return (
		<main>
			<a className="skip-link" href="#conteudo">
				Ir para o conteúdo
			</a>

			<header className="site-header shell">
				<a aria-label="contAI, início" className="brand" href="#inicio">
					<Mark />
					<span>
						cont<span>AI</span>
					</span>
				</a>
				<nav aria-label="Navegação principal">
					<a href="#rotina">Rotina</a>
					<a href="#dados">Engenharia</a>
					<a href="#conector">IA em desenho</a>
					<a href="#privacidade">Privacidade</a>
					<a href="#etapas">Entregas</a>
				</nav>
				<span className="header-status">
					<span aria-hidden="true" /> Aplicativo em desenvolvimento
				</span>
			</header>

			<section className="hero shell" id="inicio">
				<div className="hero__copy" id="conteudo">
					<p className="hero__eyebrow">
						Aplicativo para Windows · em desenvolvimento
					</p>
					<h1>Da fonte oficial à divergência na NF-e.</h1>
					<span aria-hidden="true" className="total-rule" />
					<p className="hero__lead">
						O contAI transforma fontes tributárias dispersas em uma base
						versionada e usa regras determinísticas para mostrar ao contador o
						campo, a divergência e a evidência por trás de cada alerta.
					</p>
					<div className="hero__actions">
						<a
							className="button-primary"
							href={REPO_URL}
							rel="noopener noreferrer"
							target="_blank"
						>
							Examinar o projeto
						</a>
						<a className="text-link" href="#conector">
							Ver conector de IA planejado
						</a>
					</div>
					<p className="hero__meta">
						A base tributária e o motor fiscal já funcionam. A interface desktop
						e o conector de IA estão em desenvolvimento e ainda não foram
						distribuídos.
					</p>
				</div>
				<Ledger />
			</section>

			<aside className="proof-bar" aria-label="Evidências atuais do projeto">
				<dl className="shell">
					{deliveryProof.map(([value, label]) => (
						<div key={label}>
							<dt>{value}</dt>
							<dd>{label}</dd>
						</div>
					))}
				</dl>
			</aside>

			<section className="section" id="rotina">
				<div className="shell">
					<div className="split">
						<div className="split__text">
							<p className="section-kicker">01 · O problema antes da stack</p>
							<h2>O código começou na mesa do contador.</h2>
							<p>
								Antes de escolher tecnologia, o projeto mapeou onde a informação
								fiscal é procurada, o que muda com o tempo e o que precisa ficar
								provado numa revisão. As seis fontes ao lado viraram uma base
								única sem perder procedência, captura ou versão.
							</p>
						</div>
						<SourcesToBase />
					</div>

					<table className="pair">
						<caption>O que o contador precisa e como o contAI responde</caption>
						<thead>
							<tr>
								<th scope="col">Na mesa do contador</th>
								<th scope="col">No contAI</th>
							</tr>
						</thead>
						<tbody>
							{translation.map((row) => (
								<tr key={row.desk}>
									<th scope="row">{row.desk}</th>
									<td>{row.product}</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			</section>

			<section className="section section--paper" id="dados">
				<div className="shell">
					<div className="heading">
						<div>
							<p className="section-kicker">02 · Entrega de ponta a ponta</p>
							<h2>Fonte, banco, regra e interface no mesmo sistema.</h2>
						</div>
						<p>
							Não é um mockup isolado. A entrega atravessa captura em Python,
							qualidade, SQL versionado, PostgreSQL, CI e regras fiscais que
							podem ser repetidas offline.
						</p>
					</div>

					<ol className="flow">
						{flow.map((step, index) => (
							<li key={step.name} style={vars({ "--t": index })}>
								<span className="flow__node" data-tier={index}>
									{step.name}
								</span>
								<p>{step.text}</p>
							</li>
						))}
					</ol>

					<div className="status">
						<table className="ledger-table">
							<caption>Estado da base no ambiente de desenvolvimento</caption>
							<thead>
								<tr>
									<th scope="col">Fonte</th>
									<th scope="col">Estado</th>
									<th scope="col">Observação</th>
								</tr>
							</thead>
							<tbody>
								{baseStatus.map((row) => (
									<tr key={row.source}>
										<th scope="row">{row.source}</th>
										<td>
											<span className="chip" data-state={row.state}>
												{row.state}
											</span>
										</td>
										<td>{row.note}</td>
									</tr>
								))}
							</tbody>
							<tfoot>
								<tr>
									<th colSpan={2} scope="row">
										Blocos de norma estruturados
									</th>
									<td className="mono">
										<span className="ledger__total">
											<CountUp to={12966} />
										</span>
									</td>
								</tr>
							</tfoot>
						</table>

						<div className="status__side">
							<p>
								As seis fontes têm execução verde no GitHub Actions. O ambiente
								de desenvolvimento preserva 34 payloads brutos, totalizando
								20.563.634 bytes verificados. A cobertura jurídica é parcial e
								não houve carga em produção.
							</p>
							<dl className="principles">
								{principles.map(([term, text]) => (
									<div key={term}>
										<dt>{term}</dt>
										<dd>{text}</dd>
									</div>
								))}
							</dl>
						</div>
					</div>
				</div>
			</section>

			<section className="section section--night" id="conector">
				<div className="shell">
					<div className="heading heading--wide">
						<div>
							<p className="section-kicker">03 · Próximo experimento</p>
							<h2>A IA entra depois da base confiável.</h2>
						</div>
						<p>
							O diagrama abaixo demonstra um contrato pretendido: consulta
							somente de leitura, resposta com procedência e recusa quando a
							cobertura não permite concluir. O conector ainda não foi
							implementado.
						</p>
					</div>

					<Connector />

					<div className="connector-more">
						<table className="ledger-table ledger-table--dark">
							<caption>Capacidades do contrato em estudo</caption>
							<thead>
								<tr>
									<th scope="col">Consulta</th>
									<th scope="col">Pergunta de exemplo</th>
									<th scope="col">O que volta</th>
								</tr>
							</thead>
							<tbody>
								{connectorContract.map((tool) => (
									<tr key={tool.name}>
										<th className="mono" scope="row">
											{tool.name}
										</th>
										<td>{tool.ask}</td>
										<td>{tool.returns}</td>
									</tr>
								))}
							</tbody>
						</table>

						<div className="steps">
							<h3>O trilho antes da resposta</h3>
							<ol>
								{steps.map((step) => (
									<li key={step}>{step}</li>
								))}
							</ol>
							<p className="steps__field">
								<span>Estado da integração</span>
								<code>contrato em desenho · nenhuma API publicada</code>
							</p>
						</div>
					</div>
				</div>
			</section>

			<section className="section" id="privacidade">
				<div className="shell">
					<div className="heading">
						<div>
							<p className="section-kicker">04 · Decisão de arquitetura</p>
							<h2>O XML do cliente não precisa subir para a nuvem.</h2>
						</div>
						<p>
							O fluxo foi desenhado para a conferência acontecer localmente. A
							base central guarda dados tributários públicos e suas versões, não
							o acervo de notas fiscais.
						</p>
					</div>

					<div className="lanes">
						<div className="lane">
							<h3>No computador do contador</h3>
							<ol>
								<li>XML ou ZIP de NF-e</li>
								<li>Motor fiscal offline já implementado</li>
								<li>Interface e histórico em SQLite planejados</li>
							</ol>
						</div>
						<div className="wall" aria-hidden="true">
							<span>Nenhuma nota passa</span>
							<i />
							<svg
								aria-hidden="true"
								className="wall__arrow"
								viewBox="0 0 96 16"
							>
								<path d="M94 8H4M11 2 4 8l7 6" />
							</svg>
							<span className="wall__down">Só referências públicas chegam</span>
							<i />
						</div>
						<div className="lane lane--public">
							<h3>Na base pública</h3>
							<ol>
								<li>Fontes oficiais</li>
								<li>Base versionada no ambiente dev</li>
								<li>Conector de IA em desenho</li>
							</ol>
						</div>
					</div>

					<dl className="guardrails">
						{guardrails.map(([term, text]) => (
							<div key={term}>
								<dt>{term}</dt>
								<dd>{text}</dd>
							</div>
						))}
					</dl>
				</div>
			</section>

			<section className="section section--paper" id="etapas">
				<div className="shell">
					<div className="heading">
						<div>
							<p className="section-kicker">05 · Entregas e limites</p>
							<h2>O que está em uso, em validação e no papel.</h2>
						</div>
						<p>
							Cada etapa tem critérios de aceite e testes. O estado abaixo
							separa implementação real de intenção de produto, sem preencher
							lacunas com promessas.
						</p>
					</div>
					<ol className="roadmap">
						{roadmap.map((item) => (
							<li data-state={item.state} key={item.name}>
								<span aria-hidden="true" className="roadmap__dot" />
								<div>
									<h3>{item.name}</h3>
									<p>{item.text}</p>
								</div>
								<span className="chip" data-state={item.state}>
									{item.label}
								</span>
							</li>
						))}
					</ol>
				</div>
			</section>

			<section className="section" id="perguntas">
				<div className="shell split split--faq">
					<div className="split__text">
						<h2>Perguntas que um contador faria.</h2>
					</div>
					<div className="faq">
						{faq.map((item) => (
							<details key={item.q}>
								<summary>{item.q}</summary>
								<p>{item.a}</p>
							</details>
						))}
					</div>
				</div>
			</section>

			<section className="closing">
				<div className="shell">
					<h2>Código aberto. Evidência verificável. Limites à vista.</h2>
					<span aria-hidden="true" className="total-rule total-rule--light" />
					<div className="closing__actions">
						<a
							className="button-primary button-primary--light"
							href={REPO_URL}
							rel="noopener noreferrer"
							target="_blank"
						>
							Examinar código e decisões
						</a>
						<span className="closing__status">
							Aplicativo Windows + conector de IA · em desenvolvimento
						</span>
					</div>
					<p className="legal-note">
						O contAI é uma ferramenta de apoio. A ausência de alertas não
						representa conformidade fiscal integral nem substitui a revisão
						profissional ou a autorização da SEFAZ. As conversas e os dados
						mostrados nesta página são ilustrativos.
					</p>
				</div>
			</section>

			<footer className="site-footer">
				<div className="shell">
					<a
						aria-label="contAI, voltar ao início"
						className="brand brand--footer"
						href="#inicio"
					>
						<Mark />
						<span>
							cont<span>AI</span>
						</span>
					</a>
					<p>Dados fiscais com fonte.</p>
					<span>© 2026 contAI</span>
				</div>
			</footer>
		</main>
	);
}
