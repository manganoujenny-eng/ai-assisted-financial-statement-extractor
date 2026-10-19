/* The EB-PARTNERS AUDIT mark: the official "EBP – Audit" symbol from
 * https://www.eb-partnersgroup.cm/index.php/audit-and-cac-services/
 * next to the name and line used on that page.
 *
 * The symbol is read from the app's own copy (frontend/public/brand/
 * eb-audit-symbol.png). If that copy is missing it falls back to the file on
 * the EB-Partners website, and if that cannot load either, only the name is
 * shown — the logo is never redrawn or replaced by something else.
 */

import { useState } from 'react'

export const LOCAL_SYMBOL = '/brand/eb-audit-symbol.png'
export const OFFICIAL_SYMBOL =
  'https://www.eb-partnersgroup.cm/wp-content/uploads/2025/01/symbole_eb_audit-01.png'

export function BrandSymbol({ className = 'brand-symbol' }) {
  const [src, setSrc] = useState(LOCAL_SYMBOL)
  if (!src) return null
  return (
    <img
      className={className}
      src={src}
      alt="EB-Partners Audit"
      width="450"
      height="500"
      onError={() => setSrc(src === LOCAL_SYMBOL ? OFFICIAL_SYMBOL : null)}
    />
  )
}

export default function BrandMark({ showText = true }) {
  return (
    <span className="brand">
      <BrandSymbol />
      {showText && (
        <span className="brand-text">
          <span className="brand-name">EB-PARTNERS AUDIT</span>
          <span className="brand-tagline">Audit and Advisory</span>
        </span>
      )}
    </span>
  )
}