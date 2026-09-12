/** One sentence at the top of every screen saying what question it answers — for the judge
 *  who has never seen the spec, in words, before a single number. */
export function Intro({ q, a }: { q: string; a: string }) {
  return (
    <div className="intro">
      <span className="q">{q}</span>
      <span className="a">{a}</span>
    </div>
  );
}
