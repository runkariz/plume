/**
 * The Plume mark in the header and on the sign-in card: the owner's dark mark on the light theme and the white one
 * on the dark theme (small 96 px variants of the original files). Both are in the page and CSS shows the one that
 * matches the theme, so the theme toggle needs no state and nothing flashes. Decorative: the link around it has the
 * accessible name.
 */
export function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <>
      <img
        className="brand-mark brand-mark-light"
        src="/plume-mark-dark-96.png"
        alt=""
        width={size}
        height={size}
      />
      <img
        className="brand-mark brand-mark-dark"
        src="/plume-mark-white-96.png"
        alt=""
        width={size}
        height={size}
      />
    </>
  );
}
