export type AssistantId = "chatgpt" | "gemini" | "claude";

export function Glyph({ id }: { id: AssistantId }) {
	const label = { chatgpt: "CG", gemini: "GM", claude: "CL" }[id];
	return (
		<text className="assistant-monogram" x="12" y="16">
			{label}
		</text>
	);
}

export function GlyphIcon({
	id,
	size = 20,
}: {
	id: AssistantId;
	size?: number;
}) {
	return (
		<svg aria-hidden="true" height={size} viewBox="0 0 24 24" width={size}>
			<Glyph id={id} />
		</svg>
	);
}
