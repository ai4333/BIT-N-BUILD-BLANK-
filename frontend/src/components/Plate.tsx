/** The console window. One border, one header, no chrome that does not name something. */
import type { ReactNode } from "react";

interface Props {
  title: string;
  sub?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  flush?: boolean;
  style?: React.CSSProperties;
  bodyStyle?: React.CSSProperties;
}

export function Plate({ title, sub, right, children, flush, style, bodyStyle }: Props) {
  return (
    <section className="plate" style={style}>
      <header>
        <span className="glyph">▚</span>
        <span>{title}</span>
        {sub && <span className="sub">{sub}</span>}
        {right && <span className="spacer" />}
        {right}
      </header>
      <div className={flush ? "body flush" : "body"} style={bodyStyle}>
        {children}
      </div>
    </section>
  );
}
