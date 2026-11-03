const Arrow = ({ direction = "right" }: { direction?: "right" | "down" }) => (
  <svg
    aria-hidden="true"
    className={`arrow arrow--${direction}`}
    fill="none"
    viewBox="0 0 24 24"
  >
    <path d="M4 12h15M14 6l6 6-6 6" />
  </svg>
);

const Check = () => (
  <svg aria-hidden="true" className="check" fill="none" viewBox="0 0 20 20">
    <path d="m4 10 4 4 8-9" />
  </svg>
);

const productLayers = [
  {
    number: "01",
    eyebrow: "Fonte",
    title: "Dados que têm endereço.",
    body: "Tabelas e referências públicas preservam origem, captura, vigência e versão. Informação fiscal sem procedência não vira regra.",
  },
  {
    number: "02",
    eyebrow: "Regra",
    title: "Cálculo que pode ser repetido.",
    body: "O motor executa verificações determinísticas. Cada alerta identifica a regra, o campo analisado e a evidência encontrada.",
  },
  {
    number: "03",
    eyebrow: "Revisão",
    title: "Decisão continua humana.",
    body: "O contAI organiza o que merece atenção. O julgamento e a conclusão permanecem com o profissional fiscal.",
  },
];

const principles = [
  ["Local por padrão", "O XML permanece no computador no fluxo de conferência."],
  ["Evidência antes da opinião", "Alertas mostram o motivo e os limites da análise."],
  ["Tempo importa", "Regras e referências precisam respeitar a data da operação."],
];

export default function Home() {
  return (
    <main>
      <a className="skip-link" href="#conteudo">
        Ir para o conteúdo
      </a>

      <section className="hero" id="inicio">
        <header className="site-header shell">
          <a className="brand" href="#inicio" aria-label="contAI — início">
            cont<span>AI</span>
          </a>
          <nav aria-label="Navegação principal">
            <a href="#produto">Produto</a>
            <a href="#metodo">Como funciona</a>
            <a href="#principios">Princípios</a>
          </nav>
          <span className="header-status">
            <span aria-hidden="true" /> Em desenvolvimento
          </span>
        </header>

        <div className="hero-grid shell" id="conteudo">
          <div className="hero-copy">
            <p className="eyebrow">Inteligência fiscal com evidências</p>
            <h1>
              Conferência fiscal,
              <span>sem caixa-preta.</span>
            </h1>
            <p className="hero-lead">
              O contAI transforma lotes de NF-e em verificações objetivas, com regras
              determinísticas, fontes rastreáveis e evidências que o contador consegue revisar.
            </p>
            <div className="hero-action">
              <span className="coming-button" aria-disabled="true">
                Em breve <Arrow />
              </span>
              <p>
                Primeira versão para Windows
                <span>Processamento local</span>
              </p>
            </div>
          </div>

          <figure className="product-stage">
            <figcaption className="visually-hidden">Prévia ilustrativa do produto contAI</figcaption>
            <div className="stage-number" aria-hidden="true">
              55
            </div>
            <svg className="stage-lines" viewBox="0 0 720 720" aria-hidden="true">
              <path d="M-10 520C120 430 158 250 305 273s123 203 276 121 108-247 184-269" />
              <path d="M-21 574c139-99 196-217 326-184s115 183 270 107 139-223 222-222" />
              <path d="M-30 625c170-87 210-157 331-119s136 135 278 69 152-167 223-162" />
            </svg>

            <article className="product-window">
              <div className="window-bar">
                <div className="window-brand">contAI / conferência</div>
                <div className="window-live">
                  <span aria-hidden="true" /> local
                </div>
              </div>
              <div className="window-body">
                <div className="window-heading">
                  <div>
                    <span>Lote demonstrativo</span>
                    <strong>Documentos analisados</strong>
                  </div>
                  <span className="window-progress">24 / 40</span>
                </div>
                <div className="progress-track" aria-hidden="true">
                  <span />
                </div>
                <div className="document-row document-row--clear">
                  <span className="document-index">01</span>
                  <div>
                    <strong>NF-e · modelo 55</strong>
                    <span>Estrutura e totais conferidos</span>
                  </div>
                  <span className="document-state">
                    <Check /> sem alertas
                  </span>
                </div>
                <div className="document-row document-row--alert">
                  <span className="document-index">02</span>
                  <div>
                    <strong>Total de produtos</strong>
                    <span>Regra W07 · evidência disponível</span>
                  </div>
                  <span className="document-state">revisar</span>
                </div>
                <div className="evidence-line">
                  <span>campo</span>
                  <code>ICMSTot / vProd</code>
                  <span>diferença</span>
                  <code>R$ 1,00</code>
                </div>
              </div>
              <footer className="window-footer">
                <span>Prévia ilustrativa</span>
                <span>Nenhum XML enviado</span>
              </footer>
            </article>

            <div className="stage-caption">
              <span>01</span>
              <p>
                O documento entra.
                <strong>A evidência aparece.</strong>
              </p>
            </div>
          </figure>
        </div>

        <aside className="hero-ticker" aria-label="Características do produto">
          <div>
            <span>NF-e modelo 55</span>
            <i aria-hidden="true" />
            <span>Regras determinísticas</span>
            <i aria-hidden="true" />
            <span>Fontes rastreáveis</span>
            <i aria-hidden="true" />
            <span>Privacidade local</span>
          </div>
        </aside>
      </section>

      <section className="statement" id="produto">
        <div className="shell statement-grid">
          <p className="section-index">02 / O produto</p>
          <div>
            <p className="statement-kicker">Menos caça ao erro. Mais clareza para decidir.</p>
            <h2>
              Um alerta só é útil quando explica
              <em> o que encontrou.</em>
            </h2>
          </div>
          <p className="statement-aside">
            O contAI não tenta substituir o contador. Ele prepara o terreno: organiza o lote,
            executa o que pode ser verificado e deixa a evidência pronta para revisão.
          </p>
        </div>
      </section>

      <section className="method shell" id="metodo">
        <div className="method-intro">
          <p className="section-index">03 / Como funciona</p>
          <h2>Da fonte à decisão, sem salto de fé.</h2>
          <p>
            Três camadas independentes deixam a análise reproduzível e a responsabilidade no
            lugar certo.
          </p>
        </div>

        <div className="layer-list">
          {productLayers.map((layer) => (
            <article className="layer" key={layer.number}>
              <div className="layer-number">{layer.number}</div>
              <p>{layer.eyebrow}</p>
              <h3>{layer.title}</h3>
              <span>{layer.body}</span>
              <Arrow direction="down" />
            </article>
          ))}
        </div>
      </section>

      <section className="proof">
        <div className="proof-graphic" aria-hidden="true">
          <div className="proof-orbit proof-orbit--one" />
          <div className="proof-orbit proof-orbit--two" />
          <div className="proof-core">
            <span>regra</span>
            <strong>≠</strong>
            <span>opinião</span>
          </div>
        </div>
        <div className="proof-copy">
          <p className="section-index">04 / O princípio</p>
          <h2>A resposta vem com prova.</h2>
          <p>
            Campo analisado, regra executada, valor observado e limitação conhecida. O resultado
            pode ser conferido — não apenas aceito.
          </p>
          <div className="proof-code">
            <span>regra</span>
            <code>W07 · total de produtos</code>
            <span>estado</span>
            <code>evidência registrada</code>
          </div>
        </div>
      </section>

      <section className="principles shell" id="principios">
        <div className="principles-heading">
          <p className="section-index">05 / O que não negociamos</p>
          <h2>Software fiscal deve ser discreto, preciso e explicável.</h2>
        </div>
        <ol>
          {principles.map(([title, description], index) => (
            <li key={title}>
              <span>0{index + 1}</span>
              <strong>{title}</strong>
              <p>{description}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="closing">
        <div className="closing-mark" aria-hidden="true">
          cAI
        </div>
        <div className="shell closing-content">
          <p className="section-index">06 / Próximo passo</p>
          <h2>
            Estamos preparando uma nova forma de
            <span> revisar NF-e.</span>
          </h2>
          <div className="closing-action">
            <span className="coming-button coming-button--light" aria-disabled="true">
              Em breve <Arrow />
            </span>
            <p>Primeira versão para Windows 10 e 11.</p>
          </div>
          <p className="legal-note">
            O contAI é uma ferramenta de apoio. Ausência de alertas não representa conformidade
            fiscal integral nem substitui revisão profissional ou autorização da SEFAZ.
          </p>
        </div>
      </section>

      <footer className="site-footer">
        <div className="shell">
          <a className="brand brand--footer" href="#inicio" aria-label="contAI — voltar ao início">
            cont<span>AI</span>
          </a>
          <p>Inteligência fiscal com evidências.</p>
          <span>© 2026 contAI</span>
        </div>
      </footer>
    </main>
  );
}
