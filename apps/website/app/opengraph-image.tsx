import { ImageResponse } from "next/og";

export const alt = "contAI: da fonte oficial à divergência na NF-e";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
	return new ImageResponse(
		<div
			style={{
				background: "#f5f7fa",
				color: "#141b2b",
				display: "flex",
				flexDirection: "column",
				height: "100%",
				justifyContent: "space-between",
				padding: 72,
				width: "100%",
			}}
		>
			<div
				style={{
					alignItems: "center",
					display: "flex",
					fontSize: 40,
					fontWeight: 800,
					gap: 16,
				}}
			>
				<div
					style={{
						alignItems: "center",
						background: "#141b2b",
						borderRadius: 14,
						display: "flex",
						height: 56,
						justifyContent: "center",
						width: 56,
					}}
				>
					<div
						style={{
							background: "#4878da",
							borderRadius: 8,
							height: 14,
							width: 14,
						}}
					/>
				</div>
				<span>
					cont<span style={{ color: "#4878da" }}>AI</span>
				</span>
			</div>

			<div style={{ display: "flex", flexDirection: "column" }}>
				<span
					style={{
						fontSize: 88,
						fontWeight: 800,
						letterSpacing: -4,
						lineHeight: 1,
					}}
				>
					Da fonte oficial
				</span>
				<span
					style={{
						fontSize: 78,
						fontWeight: 800,
						letterSpacing: -4,
						lineHeight: 1,
					}}
				>
					à divergência na NF-e.
				</span>
				<div
					style={{
						display: "flex",
						flexDirection: "column",
						gap: 6,
						marginTop: 28,
						width: 760,
					}}
				>
					<div style={{ background: "#141b2b", height: 4, width: "100%" }} />
					<div style={{ background: "#141b2b", height: 4, width: "100%" }} />
				</div>
			</div>

			<div
				style={{
					color: "#586279",
					display: "flex",
					fontSize: 28,
					justifyContent: "space-between",
				}}
			>
				<span>Pipeline Python · motor fiscal · conector de IA planejado</span>
				<span style={{ color: "#141b2b", fontWeight: 700 }}>
					Em desenvolvimento
				</span>
			</div>
		</div>,
		size,
	);
}
