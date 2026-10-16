import { Fragment, type ReactNode } from "react";

/** The few marks the server's fixed texts use: paragraphs, "- " bullets and **bold**. Everything else is plain text
 * (no HTML is ever injected). */
export function RichText({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/);
  if (blocks.length === 1 && !text.includes("\n")) return <>{bold(text)}</>;     // one line: inline, no paragraph
  return (
    <>
      {blocks.map((b, i) => {
        const lines = b.split("\n");
        if (lines.every((l) => l.startsWith("- "))) {
          return <ul key={i} style={{ margin: "4px 0", paddingLeft: 20 }}>{lines.map((l, j) => <li key={j}>{bold(l.slice(2))}</li>)}</ul>;
        }
        return (
          <p key={i} style={{ margin: i ? "8px 0 0" : 0 }}>
            {lines.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{bold(l)}</Fragment>)}
          </p>
        );
      })}
    </>
  );
}

function bold(line: string): ReactNode[] {
  return line.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : <Fragment key={i}>{part}</Fragment>);
}
