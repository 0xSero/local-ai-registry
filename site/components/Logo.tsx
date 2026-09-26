// A model family's mark, as in the panel; a plain square when there is none.
export default function Logo({ family, size = 22 }: { family?: string; size?: number }) {
  const known = ["qwen", "hf"];
  const src = `/logos/${known.includes(family ?? "") ? family : "hf"}.svg`;
  return <img src={src} width={size} height={size} alt="" style={{ opacity: 0.95 }} />;
}
